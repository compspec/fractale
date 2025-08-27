import copy
import os
import re
import sys
import time

import google.generativeai as genai

import fractale.agent.defaults as defaults
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.context import get_context
from fractale.agent.decorators import save_result, timed


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
    state_variables = ["result", "error_message"]

    def __init__(
        self, use_cache=False, results_dir=None, save_incremental=False, max_attempts=None
    ):
        self.attempts = 0
        self.max_attempts = max_attempts

        # For now, assume these are for the manager.
        # They get added to other agents via the step creation
        # We can optionally save incremental result objects
        self.results_dir = results_dir or os.getcwd()
        self.save_incremental = save_incremental

        # The user can save if desired - caching the context to skip steps that already run.
        self.setup_cache(use_cache)

        # This supports saving custom logs and step (attempt) metadata
        self.init_metadata()

        # Custom initialization functions
        self.init()

    def reset_return_actions(self, context):
        """
        Check if we have requested return to manager or human and update counts.
        """
        if context.get("return_to_manager") is not None:
            self.metadata["counts"]["return_to_manager"] += 1
        if context.get("return_to_human") is not None:
            self.metadata["counts"]["return_to_human"] += 1
            del context["return_to_human"]

    def init_metadata(self):
        self.metadata = {
            "times": {},
            "assets": {},
            "failures": [],
            "counts": {"retries": 0, "return_to_manager": 0, "return_to_human": 0},
        }

    @save_result
    def run(self, context):
        """
        Run the agent - a wrapper around internal function _run that prepares it.
        """
        # Load cached context. This is assumed to override user provided args
        # If we have a saved context, we assume we want to use it, return early
        cached_context = self.load_cache()
        if cached_context:

            # Print the cached result, if we have it
            self.print_result(cached_context.get("result"))
            return get_context(cached_context)

        # Otherwise, create new context - set max attempts
        context = get_context(context)
        context.max_attempts = self.max_attempts or context.get("max_attempts")

        # Run, wrapping with a load and save of cache
        # This will return here when the internal loop is done
        context = self.run_step(context)
        self.save_cache(context)
        return context

    def init(self):
        pass

    def print_result(self, result):
        """
        Print a result object, if it exists.
        """
        pass

    def reset_context(self, context):
        """
        Remove output and any stateful variables. This is assuming we
        are starting again.
        """
        for key in self.state_variables:
            if key in context:
                del context[key]

        # Since we will try again, let's move current metadata into a subsection
        metadata = copy.deepcopy(self.metadata)

        # We don't want this to recurse forever
        failures = metadata.get("failures") or []
        if "failures" in metadata:
            del metadata["failures"]
        failures.append(metadata)

        # Reset metadata, save retries
        self.init_metadata()
        self.metadata["failures"] = failures
        self.metadata["counts"]["retries"] = metadata["counts"]["retries"]

        # We don't need a return here, but let's be explicit
        return context

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
        return self.attempts > self.max_attempts

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
        pattern = f"```(?:{code_type})?\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        if content.startswith(f"```{code_type}"):
            content = content[len(f"```{code_type}") :]
        if content.startswith("```"):
            content = content[len("```") :]
        if content.endswith("```"):
            content = content[: -len("```")]
        return content.strip()

    def run_step(self, context):
        """
        Run the agent. This expects to be called with a loaded context.
        """
        assert context
        raise NotImplementedError(f"The {self.name} agent is missing internal 'run' function")

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

    # We don't add timed here because we do it custom
    def ask_gemini(self, prompt, with_history=True):
        """
        Ask gemini adds a wrapper with some error handling.
        """
        try:
            start = time.perf_counter()
            if with_history:
                response = self.chat.send_message(prompt)
            else:
                response = self.model.generate_content(prompt)
            end = time.perf_counter()

            if self.save_incremental:
                self.save_gemini_metadata(end - start, response, with_history)

            # This line can fail. If it succeeds, return entire response
            return response.text.strip()

        except ValueError as e:
            print(f"[Error] The API response was blocked and contained no text: {str(e)}")
            return "GEMINI ERROR: The API returned an error (or stop) and we need to try again."

    def save_gemini_metadata(self, elapsed_time, response, with_history):
        """
        Save gemini response metadata and elapsed time
        """
        if "ask_gemini" not in self.metadata:
            self.metadata["ask_gemini"] = []
        self.metadata["ask_gemini"].append(
            {
                "conversation_history": with_history,
                "prompt_token_count": response.usage_metadata.prompt_token_count,
                "candidates_token_count": response.usage_metadata.candidates_token_count,
                "total_token_count": response.usage_metadata.total_token_count,
                "time_seconds": elapsed_time,
            }
        )
