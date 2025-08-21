import re
import textwrap

from rich import print

import fractale.agent.errors.prompts as prompts
import fractale.agent.logger as logger
import fractale.agent.results.prompts as prompts
from fractale.agent.base import GeminiAgent


class ResultParser:
    """
    A result parser has a regular expression populated by the ResultAgent.
    It will reuse a validated regular expression to parse a new log.
    """

    def __init__(self, regular_expression=None):
        self.regular_expression = regular_expression

    def parse(self, requires, log, regular_expression=None):
        """
        Given a log, run the regular expression and ask the user to verify the metric.
        """
        self.regular_expression = regular_expression or self.regular_expression

        # If we haven't derived a regular expression, ask the agent
        if not self.regular_expression:
            agent = ResultAgent()
            self.regular_expression = agent.run(requires, log)

        return re.findall(self.regular_expression, log)


def confirm_correct(log, result):
    """
    Ask the user to validate the response.
    """
    GREEN = "\033[92m"
    RESET = "\033[0m"
    prompt = f"{log}\nResult: {GREEN}{result}{RESET}\n\nPlease confirm the parsing agent result above is correct."
    while True:
        response = input(prompt + " (yes/no): ").lower().strip()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")


class ResultAgent(GeminiAgent):
    """
    Result parsing agent
    """

    name = "result"
    description = "result parsing agent"

    def run(self, requires, log):
        """
        Run the agent. This is a helper agent, so it just does a simple task.

        There is also no relevance or concept of a cache (at least for now)
        """

        # This prompt will ask the LLM to parse a result by generating
        # a regular expression. The regular expression will need validation
        # by the user, so it is a collaborative process. If the user wants
        # to provide a regular expression to the optimization parser, that
        # would bypass this step.
        prompt = prompts.parsing_prompt % (requires, log)
        print("Sending result parser prompt to Gemini...")

        # If the prompt has previous error, this can get too long for user to see
        print(textwrap.indent(prompt[0:1000], "> ", predicate=lambda _: True))

        # Keep trying until we at least get a match
        match = None
        while not match:
            regex = self.ask_gemini(prompt)
            print("Received result parser from Gemini...")
            logger.custom(regex, title="[green]Result Parser[/green]", border_style="green")
            match = re.findall(regex, log)
            if not match:
                prompt += f"\nHere is a previous unsuccessful attempt: {regex}"
                continue

            # If we get a match, ask the user to verify
            result = match[0]
            if len(match) > 1:
                result = " ".join(match)
            if confirm_correct(log, result):
                return regex

            # If it's not correct, we need to try again
            match = None
