import argparse
import copy
import json
import os
import sys
import textwrap

import google.generativeai as genai
from rich import print

import fractale.agent.build.prompts as prompts
import fractale.agent.defaults as defaults
import fractale.agent.logger as logger
import fractale.agent.scaling.prompts as prompts
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.decorators import timed


def confirm_stop():
    """
    Ask the user to confirm stopping.
    """
    prompt = "The scaling agent has decided to STOP. Do you agree?"
    while True:
        response = input(prompt + " (yes/no/feedback): ").lower().strip()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        elif response == "feedback":
            return None
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")


class ScalingAgent(GeminiAgent):
    """
    Scaling Agent

    The scaling agent is responsible for orchestrating a scaling study.
    """

    name = "scaling agent"
    description = "scaling study agent"
    state_variables = ["scale", "sizes"]

    def init(self):
        self.model = genai.GenerativeModel(defaults.gemini_model)
        self.chat = self.model.start_chat()
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")

        # We will save figures of merit, and attempt crds
        self.metadata["assets"]["results"] = {}

        # Keep a lookup of scale attempts by size
        self.metadata["scale_attempts"] = {}

    def update_scaling_size(self, context):
        """
        Ask the user for a scaling size, within current and remaining.
        """
        sizes = list(set(context.sizes + [context.size]))
        prompt = f"Please select a size to try again at: {sizes}"
        while True:
            response = input(prompt)
            try:
                size = int(response)
                if size in sizes:
                    context.size = size
                    attempts = context.get("scaling_attempts")
                    if attempts is not None and size in attempts:
                        del context.scaling_attempts[size]
                    if size not in context.sizes:
                        # Add size at first position
                        context.sizes.insert(0, size)
                    return context
            except:
                pass
            print(f"Invalid input. Please select from {sizes}")

    def _add_arguments(self, subparser):
        """
        Add arguments for the plugin to show up in argparse
        """
        agent = subparser.add_parser(
            self.name,
            formatter_class=argparse.RawTextHelpFormatter,
            description=self.description,
        )
        agent.add_argument(
            "instruction",
            help="Scaling instruction (include application, environment, algorithm, etc.).",
        )
        return agent

    def get_scaling_prompt(self, context):
        """
        Get the scaling prompt.
        """
        run_config = context.optimize_result["final"]
        best_fom = context.optimize_result["best_fom"]

        # If requirements not specified, we require the "optimize" context
        return prompts.get_scaling_prompt(context, run_config=run_config, best_fom=best_fom)

    @timed
    def run(self, context, prompt=None, additional=""):
        """
        Run the scaling agent.

        Additional text can reset each time.
        """
        # We don't do attempts because we have no condition for success.
        context = get_context(context)

        # We get the best fom and result (configuration for run)
        if prompt is None:
            prompt = self.get_scaling_prompt(context)
        print("Sending scaling prompt to Gemini...")

        # Get the updates. We assume that optimization updates for resources
        # need to come back and be parsed into json.
        print(textwrap.indent(prompt[0:500], "> ", predicate=lambda _: True))

        while True:
            content = self.ask_gemini(prompt + "\n" + additional, with_history=True)
            print("Received optimization from Gemini...")
            logger.custom(content, title="[green]Scaling Agent[/green]", border_style="green")
            try:
                result = json.loads(self.get_code_block(content, "json"))
                break
            except:
                prompt += "You MUST return the variables back in json"

        # This is an invalid result.
        if "decision" not in result or "reason" not in result:
            additional = "The JSON MUST have the fields 'decision', 'reason' at the top level with the manifest."
            return self.run(context, prompt, additional)

        if result["decision"] not in ["STOP", "PROCEED"]:
            additional = "The JSON 'decision' MUST be STOP or PROCEED.."
            return self.run(context, prompt, additional)

        # If we get a stop, check with the user first.
        if result["decision"] == "STOP":
            stop_decision = confirm_stop()

            # Choose the size
            if stop_decision in [None, False]:
                context = self.update_scaling_size(context)
                prompt = self.get_scaling_prompt(context)

            if stop_decision is None:
                additional = input("Please enter feedback for the LLM:\n")
                return self.run(context, prompt, additional)

            # Don't stop (implication is to retry the size)
            elif stop_decision is False:
                additional = f"The user has requested that you NOT stop."
                return self.run(context, prompt, additional)

        context.scaling_result = result
        return context
