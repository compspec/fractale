import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

import google.generativeai as genai
from rich import print

import fractale.agent.defaults as defaults
import fractale.agent.flux.batch.prompts as prompts
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.decorators import timed
from fractale.agent.errors import DebugAgent


class FluxBatchAgent(GeminiAgent):
    """
    Flux JobSpec Agent

    Create or translate Flux Framework JobSpecs.
    """

    name = "flux-batch"
    description = "Flux batch agent"
    state_variables = ["instruction"]

    def init(self):
        self.model = genai.GenerativeModel(defaults.gemini_model)
        self.chat = self.model.start_chat()
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")
        self.metadata["generation_attempts"] = 0

    def _add_arguments(self, subparser):
        """
        Add arguments for the plugin to show up in argparse
        """
        agent = subparser.add_parser(
            self.name,
            formatter_class=argparse.RawTextHelpFormatter,
            description=self.description,
        )
        agent.add_argument("instruction", help="Jobspec generation instruction")
        return agent

    @timed
    def run(self, context, prompt=None):
        """
        Run the optimization agent.

        Additional text can reset each time.
        """
        # We don't do attempts because we have no condition for success.
        context = get_context(context)
        prompt = prompt or prompts.get_generate_prompt(context)
        self.metadata["generation_attempts"] += 1

        # validator.parse(jobspec)

        print("Sending jobspec request prompt to Gemini...")
        print(textwrap.indent(prompt[0:500], "> ", predicate=lambda _: True))

        content = self.ask_gemini(prompt, with_history=True)
        print("Received jobspec from Gemini...")
        logger.custom(content, title="[green]Result Parser[/green]", border_style="green")
        try:
            result = self.get_code_block(content, "bash")
            return_code, output = self.validate(context, result)
            context.result = output
            if return_code == 0:
                self.print_result(context.result)
                logger.success(f"Valid Flux Batch Job in {self.attempts} attempts")
            else:
                logger.error(f"Validation failed:\n{output}")

                # Get DebugAgent insights!
                print("\n[bold cyan] Requesting Correction from Debug Agent[/bold cyan]")
                context.error_message = output
                context = DebugAgent().run(context, requires=[output])

                # If we have reached the max attempts...
                if self.reached_max_attempts() or context.get("return_to_manager") is True:
                    context.return_to_manager = False

                    # If we are being managed, return the result
                    if context.is_managed():
                        context.return_code = -1
                        context.result = context.error_message
                        return context

                    # Otherwise this is a failure state
                    logger.exit(f"Max attempts {self.max_attempts} reached.", title="Agent Failure")

                # If we get here, invalid and we need to try again
                self.attempts += 1
                return self.run(context)

        except:
            prompt += "\nYou MUST return the variables back as a bash script"
            return self.run(context, prompt)

        # If we get here, we had success and return
        return context

    def validate(self, context, content):
        """
        Validate a generated Flux batch script.
        """
        container = context.get("container", default="ghcr.io/compspec/fractale:flux-validator")
        validate_dir = tempfile.mkdtemp()
        batch_script = os.path.join(validate_dir, "batch.sh")
        utils.write_file(content, batch_script)
        utils.make_executable(batch_script)
        uid = os.getuid()
        gid = os.getgid()
        cmd = [
            "docker",
            "run",
            "-v",
            "./:/data/",
            "-it",
            "-u",
            f"{uid}:{gid}",
            container,
            "/data/batch.sh",
        ]
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=validate_dir,
            check=False,
        )
        # Clean up after we finish
        shutil.rmtree(validate_dir, ignore_errors=True)
        return (p.returncode, p.stdout + p.stderr)
