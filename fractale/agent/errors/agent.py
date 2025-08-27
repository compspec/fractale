import textwrap

from rich import print

import fractale.agent.errors.prompts as prompts
import fractale.agent.logger as logger
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context


class DebugAgent(GeminiAgent):
    """
    Debug agent.
    """

    name = "debug"
    description = "error debugging agent"

    def __init__(self, *args, **kwargs):
        """
        Add the optimization agent, even if we don't need it.
        """
        super().__init__(*args, **kwargs)
        # Debug agents are usually ephemeral, but if not used like that, keep record
        self.metadata["assets"]["counts"] = {"return_to_manager": 0, "return_to_human": 0}

    def get_prompt(self, context, requires=None):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)
        return prompts.get_debug_prompt(context, requires=requires)

    def run(self, context, requires=None):
        """
        Run the agent. This is a helper agent, so it just does a simple task.

        There is also no relevance or concept of a cache (at least for now)
        """
        # We don't do attempts because we have no condition for success.
        context = get_context(context)

        # This prompt will ask the LLM to inspect a piece of code and the error,
        # and write a suggested fix (prompt for calling agent)
        # The requires are requirements for the fix (e.g., hints
        # about what not to do)
        prompt = self.get_prompt(context, requires=requires)
        print("Sending debug prompt to Gemini...")

        # If the prompt has previous error, this can get too long for user to see
        print(textwrap.indent(prompt[0:1000], "> ", predicate=lambda _: True))
        content = self.ask_gemini(prompt)
        print("Received debugging advice from Gemini...")
        logger.custom(content, title="[green]Debug Advice[/green]", border_style="green")

        # Do we have instructions to return to the manager?
        if "RETURN TO MANAGER" in content:
            logger.custom(
                "Error debugging agent has recommended return to manager",
                title="[blue]Debug Advice[/blue]",
                border_style="blue",
            )
            content = content.replace("RETURN TO MANAGER", "")
            context.return_to_manager = True
            self.metadata["assets"]["counts"]["return_to_manager"] += 1

        if "RETURN TO HUMAN" in content:
            logger.custom(
                "Error debugging agent has requested human feedback. Please add text to 'content' and then type '%store content' and 'exit'",
                title="[blue]Debug Advice[/blue]",
                border_style="blue",
            )
            context.return_to_human = True
            self.metadata["assets"]["counts"]["return_to_human"] += 1
            content += "\n" + input("Please provide additional input as requested:\n")

        # The tweaked output as the advice for next step (instead of entire error output)
        context.error_message = content

        # Helper agents always return context back
        return context
