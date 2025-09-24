import textwrap

from rich import print

import fractale.agent.cost.prompts as prompts
import fractale.agent.logger as logger
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context


class CostAgent(GeminiAgent):
    """
    Debug agent.
    """

    name = "cost"
    description = "cost estimation agent"

    def get_prompt(self, context):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)
        return prompts.get_estimation_prompt(context)

    def run(self, context):
        """
        Run the agent. This is a helper agent, so it just does a simple task.
        """
        context = get_context(context)

        # Ask the agent about estimating cost.
        prompt = self.get_prompt(context)
        print("Sending cost estimation prompt to Gemini...")

        # If the prompt has previous error, this can get too long for user to see
        print(textwrap.indent(prompt[0:1000], "> ", predicate=lambda _: True))
        content = self.ask_gemini(prompt)
        print("Received cost estimation advice from Gemini...")
        logger.custom(content, title="[green]Cost Estimation Advice[/green]", border_style="green")
        context.result = self.get_code_block(content, "json")

        # Helper agents always return context back
        return context
