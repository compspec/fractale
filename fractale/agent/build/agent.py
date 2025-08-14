from fractale.agent.base import GeminiAgent
import fractale.agent.build.prompts as prompts
from fractale.agent.context import get_context
from fractale.agent.errors import DebugAgent
import fractale.agent.logger as logger
import fractale.utils as utils
import argparse

from rich import print
from rich.syntax import Syntax

import re
import os
import sys
import shutil
import tempfile
import subprocess
import textwrap


# regular expression in case LLM does not follow my instructions!
dockerfile_pattern = r"```(?:dockerfile)?\n(.*?)```"


class BuildAgent(GeminiAgent):
    """
    Builder agent.

    Observations from v:
    1. Holding the context (chat) seems to take longer.
    2. Don't forget to ask for CPU - GPU will take a lot longer.
    """

    name = "build"
    description = "builder agent"

    def _add_arguments(self, subparser):
        """
        Add arguments for the plugin to show up in argparse
        """
        build = subparser.add_parser(
            self.name,
            formatter_class=argparse.RawTextHelpFormatter,
            description=self.description,
        )
        build.add_argument(
            "--container",
            help="Container unique resource identifier (defaults to application if not set)",
        )
        build.add_argument(
            "application",
            help="Application to build.",
        )
        build.add_argument(
            "--environment",
            help="Environment description to build for (defaults to generic)",
        )
        return build

    def get_prompt(self, context):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)

        # These are optional if we are doing a follow up build
        error_message = context.get("error_message")
        dockerfile = context.get("dockerfile")

        # If a previous dockerfile failed at runtime, we are tweaking it
        # Otherwise we prepare a new request.
        if dockerfile and error_message:
            prompt = prompts.get_rebuild_prompt(context)
        else:
            prompt = prompts.get_build_prompt(context)
        return prompt

    def filter_output(self, output):
        """
        Remove standard lines (e.g., apt install stuff) that likely won't help but
        add many thousands of tokens... (in testing, from 272K down to 2k)
        """
        skips = ["Get:", "Preparing to unpack", "Unpacking ", "Selecting previously "]
        regex = "(%s)" % "|".join(skips)
        return "\n".join([x for x in output.split("\n") if not re.search(regex, x)])

    def _run(self, context):
        """
        Run the agent.

        The design of an agent run should:

        1. Assume a prepared context (either new and populated or loaded)
        2. Call supporting functions with the context.
        3. Parse the result and update context, taking appropriate action.
        4. The current object to generate should be put into result.
        5. The current issue or error goes into error_message.
        """
        # This will either generate fresh or rebuild erroneous Dockerfile
        # We don't return the dockerfile because it is updated in the context
        self.generate_dockerfile(context)
        logger.custom(
            context.result, title="[green]Dockerfile or Response[/green]", border_style="green"
        )

        # Set the container on the context for a next step to use it...
        container = context.get("container") or self.generate_name(context.application)
        context.container = container

        # Build it! We might want to only allow a certain number of retries or incremental changes.
        return_code, output = self.build(context)
        if return_code == 0:
            self.print_result(context.result)
            logger.success(f"Build complete in {self.attempts} attempts")
        else:
            # Filter out likely not needed lines (ubuntu install)
            output = self.filter_output(output)
            logger.error(f"Build failed:\n{output[-1000:]}")
            print("\n[bold cyan] Requesting Correction from Dockerfile Build Agent[/bold cyan]")

            # Ask the debug agent to better instruct the error message
            # This becomes a more guided output
            context.error_message = output
            agent = DebugAgent()
            # This updates the error message to be the output
            context = agent.run(context, requires=prompts.requires)

            # If we have reached the max attempts...
            if self.reached_max_attempts():

                # If we are being managed, return the result
                if context.is_managed():
                    context.return_code = -1
                    context.result = context.error_message
                    return context

                # Otherwise this is a failure state
                logger.exit(f"Max attempts {self.max_attempts} reached.", title="Agent Failure")

            self.attempts += 1
            print("\n[bold cyan] Requesting Correction from Build Agent[/bold cyan]")

            # Update the context with error message
            return self.run(context)

        # Add generation line
        self.write_file(context, context.result)

        # Assume being called by a human that wants Dockerfile back,
        # unless we are being managed
        return context

    def print_result(self, dockerfile):
        """
        Print Dockerfile with highlighted Syntax
        """
        highlighted_syntax = Syntax(dockerfile, "docker", theme="monokai", line_numbers=True)
        logger.custom(
            highlighted_syntax, title="Final Dockerfile", border_style="green", expand=True
        )

    def generate_name(self, name):
        """
        If no container URI provided, generate a name based on application.
        """
        # Replace invalid characters with hyphens
        name = re.sub(r"[^a-zA-Z0-9_.-]", "-", name)

        # First character needs to be alphanumeric
        if not name[0].isalnum():
            name = "c" + name

        # Remove leading/trailing separators if they exist
        name = re.sub(r"^[._-]*", "", name)
        name = re.sub(r"[._-]*$", "", name)

        # Truncate to a maximum of 63 characters and strip crap
        name = name[:63].strip("-")

        # Ensure it's at least 2 characters long (add a 'c' if it's too short)
        if len(name) < 2:
            name = name + "c"
        return name.lower()

    def build(self, context):
        """
        Build the Dockerfile! Yolo!
        """
        dockerfile = context.get("dockerfile")

        # Not sure if this can happen, assume it can
        if not dockerfile:
            raise ValueError("No dockerfile content provided.")

        build_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary build context: {build_dir}[/dim]")

        # Write the Dockerfile to the temporary directory
        utils.write_file(dockerfile, os.path.join(build_dir, "Dockerfile"))

        # If only one max attempt, don't print here, not important to show.
        if self.max_attempts is not None and self.max_attempts > 1:
            logger.custom(
                f"Attempt {self.attempts} to build image: [bold cyan]{context.container}[/bold cyan]",
                title="[blue]Docker Build[/blue]",
                border_style="blue",
            )

        # Run the build process using the temporary directory as context
        p = subprocess.run(
            ["docker", "build", "--network", "host", "-t", context.container, "."],
            capture_output=True,
            text=True,
            cwd=build_dir,
            check=False,
        )
        # Clean up after we finish
        shutil.rmtree(build_dir, ignore_errors=True)
        return (p.returncode, p.stdout + p.stderr)

    def generate_dockerfile(self, context):
        """
        Generates or refines a Dockerfile using the Gemini API.
        """
        prompt = self.get_prompt(context)
        print("Sending build prompt to Gemini...")
        print(textwrap.indent(prompt[0:1000], "> ", predicate=lambda _: True))

        # The API can error and not return a response.text.
        content = self.ask_gemini(prompt)
        print("Received Dockerfile response from Gemini...")

        # Try to remove Dockerfile from code block
        try:
            content = self.get_code_block(content, "dockerfile")

            # If we are getting commentary...
            match = re.search(dockerfile_pattern, content, re.DOTALL)
            if match:
                dockerfile = match.group(1).strip()
            else:
                dockerfile = content.strip()

            # The result is saved as a build step
            # The dockerfile is the argument used internally
            context.result = dockerfile
            context.dockerfile = dockerfile
        except Exception as e:
            sys.exit(f"Error parsing response from Gemini: {e}\n{content}")
