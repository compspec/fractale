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
import fractale.agent.optimize.prompts as prompts
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.decorators import timed

# The result parser holds a ResultAgent
from fractale.agent.results import ResultParser


class OptimizationAgent(GeminiAgent):
    """
    Optimization Agent

    The optimization agent receives a figure of merit request
    and a need to minimize or maximize. It will return to a job
    running agent (akin to Kubernetes Job) that has explicit
    instructions to only change a subset of the execution arguments.
    This means that the optimization agent can be general to take
    some application and parameters attempted before. The optimization
    agent should return a new parameter set to the build agent.
    """

    name = "optimization"
    description = "optimization agent"
    state_variables = ["optimize"]

    def init(self):
        self.model = genai.GenerativeModel(defaults.gemini_model)
        self.chat = self.model.start_chat()
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")

        # We will save figures of merit, and attempt crds
        self.metadata["assets"]["updates"] = []
        self.metadata["assets"]["regex"] = []
        self.metadata["assets"]["regex-attempts"] = []
        self.foms = []

        # We could just take the listing of FOMs, but I am not sure
        # if there are cases where that might not reflect attempts.
        self.metadata["optimize_attempts"] = 0
        self.parser = ResultParser()

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
            "optimize",
            help="Optimization instruction (include application, environment, algorithm, etc.).",
        )
        agent.add_argument(
            "function",
            help="Request an optimization function instead",
            action="store_true",
            default=False,
        )
        return agent

    @timed
    def run(self, context, log, prompt=None, additional=""):
        """
        Run the optimization agent.

        Additional text can reset each time.
        """
        # We don't do attempts because we have no condition for success.
        context = get_context(context)

        prompt = prompt or context.get("requires")

        # If requirements not specified, we require the "optimize" context
        if context.get("function") and not prompt:
            prompt = prompts.get_function_optimize_prompt(context)
        elif not prompt:
            prompt = prompts.get_function_optimize_prompt(context)

        # Parser requires is the FOM and optimize directive.
        # This returns a list of foms.
        foms = self.parser.parse(context.optimize, log, context.get("optimize.regex"))
        self.foms += foms
        self.metadata["optimize_attempts"] += 1

        # This adds supplementary detail about how to optimize - "keep going until it's good":_
        additional = additional + "\n" if additional else ""
        prompt += additional + prompts.supplement_optimize_prompt % (
            self.metadata["optimize_attempts"],
            json.dumps(self.foms),
        )

        # TODO: if this agent stores memory we don't need to include dockerfile after the first...
        print("Sending optimization prompt to Gemini...")

        # Get the updates. We assume that optimization updates for resources
        # need to come back and be parsed into json.
        print(textwrap.indent(prompt[0:500], "> ", predicate=lambda _: True))
        
        while True:
            content = self.ask_gemini(prompt, with_history=True)
            print("Received optimization from Gemini...")
            logger.custom(content, title="[green]Result Parser[/green]", border_style="green")
            try:
                result = json.loads(self.get_code_block(content, "json"))
                break
            except:
                prompt += "You MUST return the variables back in json"

        # This is an invalid result.
        if "decision" not in result or "reason" not in result:
            additional = "The JSON MUST have the fields 'decision', 'reason' at the top level with the manifest."
            return self.run(context, log, prompt, additional)

        # We can't be sure of the format or how to update, so return to job agent
        self.metadata["assets"]["updates"].append(copy.deepcopy(result))
        self.metadata["assets"]["regex-attempts"].append(self.parser.regex_attempts)
        self.metadata["assets"]["regex"].append(self.parser.regular_expression)

        context.optimize_result = result
        return context
