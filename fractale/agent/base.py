import os
import sys

import google.generativeai as genai

from fractale.agent.decorators import callback, save_logs
import fractale.agent.defaults as defaults
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.context import get_context


class Agent:
    """
    A base for an agent. Each agent should:

    1. Have a run function that accepts (and modifies) a context.
    2. Set the context.result as the final result (or set to None)
      - On failure, set context.result to the error context.
    3. Set any other variables needed by future build steps.
    4. Optionally use a cache, which can load context for a step.
    """

    # name and description should be on the class

    def __init__(self, use_cache=False, results_dir=None, incremental=False):

        # Max attempts defaults to unlimited
        # We start counting at 1 for the user to see.
        # Eat your heart out, Matlab.
        self.attempts = 1
        self.max_attempts = None

        # For now, assume this is for the manager.
        # We can optionally save incremental result objects
        self.results_dir = results_dir or os.getcwd()
        self.save_incremental = incremental

        # The user can save if desired - caching the context to skip steps that already run.
        self.setup_cache(use_cache)

        # This supports saving custom logs and step (attempt) metadata
        self.metadata = {}

        # Custom initialization functions
        self.init()

    @callback(save_logs)
    def run(self, context):
        """
        Run the agent - a wrapper around internal function _run that prepares it.
        """
        # Init attempts. Each agent has an internal counter for total attempts
        self.attempts = self.attempts or 1

        # Load cached context. This is assumed to override user provided args
        # If we have a saved context, we assume we want to use it, return early
        cached_context = self.load_cache()
        if cached_context:

            # Print the cached result, if we have it
            self.print_result(cached_context.get("result"))
            return get_context(cached_context)

        # Otherwise, create new context
        context = get_context(context)

        # Run, wrapping with a load and save of cache
        context = self._run(context)
        self.save_cache(context)
        return context

    def init(self):
        pass

    def print_result(self, result):
        """
        Print a result object, if it exists.
        """
        pass

    def setup_cache(self, use_cache=False):
        """
        Setup (or load) a cache.
        """
        self.cache = {}
        self.use_cache = use_cache
        self.cache_dir = None

        # Cut out early if no cache.
        if not use_cache:
            return

        # Create in the current working directory.
        self.cache_dir = os.path.join(os.getcwd(), ".fractale")

    def load_cache(self):
        """
        Load context from steps. Since the agents map 1:1 (meaning we do not expect to see an agent twice)
        and the order could change), we can index based on name. Each agent is only responsible for
        loading its cache.
        """
        if self.cache_dir and os.path.exists(self.cache_file):
            logger.info(f"Loading context cache for step {self.name}")
            return utils.read_json(self.cache_file)

    @property
    def cache_file(self):
        """
        Cache file for the context - currently we just have this one.
        """
        step_path = os.path.join(self.cache_dir, self.name)
        return os.path.join(step_path, "context.json")

    def save_cache(self, context):
        """
        Save cache to file. Since this is implemented on one agent, we assume saving
        the current state when the agent is running, when it is active.
        """
        if not self.cache_dir:
            return
        cache_dir = os.path.join(self.cache_dir, self.name)
        if not os.path.exists(cache_dir):
            logger.info(f"Creating cache for saving: .fractale/{self.name}")
            os.makedirs(cache_dir)
        utils.write_json(context.data, self.cache_file)

    def reached_max_attempts(self):
        """
        On failure, have we reached max attempts and should return?
        """
        # Unset (None) or 1.
        if not self.max_attempts:
            return False
        return self.attempts >= self.max_attempts

    def set_max_attempts(self, max_attempts):
        self.max_attempts = max_attempts

    def add_shared_arguments(self, agent):
        """
        Add the agent name.
        """
        # Ensure these are namespaced to your plugin
        agent.add_argument(
            "--outfile",
            help="Output file to write Job manifest to (if not specified, only will print)",
        )
        agent.add_argument(
            "--details",
            help="Details to provide to the agent.",
        )
        # If exists, we will attempt to load and use.
        agent.add_argument(
            "--use-cache",
            dest="use_cache",
            help="Use (load and save) local cache in pwd/.fractale/<step>",
            action="store_true",
            default=False,
        )

        # This is just to identify the agent
        agent.add_argument(
            "--agent-name",
            default=self.name,
            dest="agent_name",
        )

    def add_arguments(self, subparser):
        """
        Add arguments for the agent to show up in argparse

        This is added by the plugin class
        """
        agent = self._add_arguments(subparser)
        if agent is None:
            return
        self.add_shared_arguments(agent)

    def _add_arguments(self, subparser):
        """
        Internal function to add arguments.
        """
        pass

    def write_file(self, context, content, add_comment=True):
        """
        Shared function to write content to file, if context.outfile is defined.
        """
        outfile = context.get("outfile")
        if not outfile:
            return
        # Add generation line
        if add_comment:
            content += f"\n# Generated by fractale {self.name} agent"
        utils.write_file(content, outfile)

    def get_code_block(self, content, code_type):
        """
        Parse a code block from the response
        """
        if content.startswith(f"```{code_type}"):
            content = content[len(f"```{code_type}") :]
        if content.startswith("```"):
            content = content[len("```") :]
        if content.endswith("```"):
            content = content[: -len("```")]
        return content

    def _run(self, context):
        """
        Run the agent. This expects to be called with a loaded context.
        """
        assert context
        raise NotImplementedError(f"The {self.name} agent is missing internal 'run' function")

    def get_initial_prompt(self, context):
        """
        Get the initial prompt (with details) to provide context to the manager.

        If we don't do this, the manager can provide a bad instruction for how to fix the error.
        """
        return self.get_prompt(context)

    def get_prompt(self, context):
        """
        This function should take the same context as run and return the parsed prompt that
        would be used. We do this so we can hand it to the manager for tweaking.
        """
        assert context
        raise NotImplementedError(f"The {self.name} agent is missing a 'get_prompt' function")


class GeminiAgent(Agent):
    """
    A base for an agent that uses the Gemini API.
    """

    def init(self):
        self.model = genai.GenerativeModel(defaults.gemini_model)
        self.chat = self.model.start_chat()
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")

    def ask_gemini(self, prompt, with_history=True):
        """
        Ask gemini adds a wrapper with some error handling.
        """
        try:
            if with_history:
                response = self.chat.send_message(prompt)
            else:
                response = self.model.generate_content(prompt)

            # This line can fail. If it succeeds, return entire response
            return response.text.strip()

        except ValueError as e:
            print(f"[Error] The API response was blocked and contained no text: {str(e)}")
            return "GEMINI ERROR: The API returned an error (or stop) and we need to try again."
