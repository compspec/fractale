import argparse
import copy
import json
import os
import sys
import textwrap

import google.generativeai as genai
from rich import print

import fractale.agent.defaults as defaults
import fractale.agent.logger as logger
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.decorators import timed
import fractale.agent.flux.jobspec.prompts as prompts


class FluxJobSpecAgent(GeminiAgent):
    """
    Flux JobSpec Agent

    Create or translate Flux Framework JobSpecs.
    """

    name = "flux-jobspec"
    description = "Flux jobspec agent"
    state_variables = ["instruction"]

    def init(self):
        self.model = genai.GenerativeModel(defaults.gemini_model)
        self.chat = self.model.start_chat()
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")
        self.metadata['generation_attempts'] = 0

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
    def run(self, context):
        """
        Run the optimization agent.

        Additional text can reset each time.
        """
        # We don't do attempts because we have no condition for success.
        context = get_context(context)
        prompt = prompts.get_generate_prompt(context)
        self.metadata["generation_attempts"] += 1

        # validator.parse(jobspec)

        print("Sending jobspec request prompt to Gemini...")
        print(textwrap.indent(prompt[0:500], "> ", predicate=lambda _: True))

        while True:
            content = self.ask_gemini(prompt, with_history=True)
            print("Received jobspec from Gemini...")
            logger.custom(content, title="[green]Result Parser[/green]", border_style="green")
            import IPython 
            IPython.embed()
            try:
                result = json.loads(self.get_code_block(content, "json"))
                break
            except:
                prompt += "You MUST return the variables back in json"

        # We can't be sure of the format or how to update, so return to job agent
        self.metadata["assets"]["updates"].append(copy.deepcopy(result))
        self.metadata["assets"]["regex-attempts"].append(self.parser.regex_attempts)
        self.metadata["assets"]["regex"].append(self.parser.regular_expression)

        context.jobspec = result
        return context
