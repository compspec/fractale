import fractale.utils as utils
from fractale.selector import get_selector


class TransformerBase:
    """
    A Transformer base converts a Flux jobspec into something else.

    It loads a Jobspec and transforms for a particular environment
    (which typically means a workload manager or similar). This is most
    relevant for submit and batch commands, along with custom steps.
    This can be very manual, or use an LLM.
    """

    def __init__(self, selector="random", solver=None):
        """
        Create a new transformer backend, accepting any options type.

        Validation of transformers is done by the registry
        """
        self.selector = get_selector(selector)
        self.solver = solver

    def _parse(self, *args, **kwargs):
        """
        Parse converts the native jobspec to the standard JobSpec
        """
        raise NotImplementedError

    def parse(self, filename):
        return self._parse(filename)

    def unhandled(self, filename):
        return self._parse(filename, return_unhandled=True)

    def convert(self, *args, **kwargs):
        """
        Convert a normalized jobspec to the format here.
        """
        raise NotImplementedError

    def render(self, matches, jobspec):
        """
        Run the transformer:

        1. Select some number of matches.
        2. Transform into a batch script.
        """
        js = utils.load_jobspec(jobspec)
        return self.run(matches, js)


class Script:
    """
    A helper class to build a batch script line by line.
    """

    def __init__(self, directive=""):
        self.script_lines = ["#!/bin/bash"]
        self.directive = directive

    def newline(self):
        self.script_lines.append("")

    def add_line(self, line: str):
        """
        Add a custom line to the script.
        """
        self.script_lines.append(line)

    def add(self, name: str, value=None):
        """
        Add a Flux directive, e.g., #FLUX: --job-name=my-job or #FLUX: -N 4.
        Handles both short and long options.
        """
        if value is None:
            return

        # Determine if it's a short (-n) or long (--tasks) option
        prefix = "-" if len(name) == 1 else "--"
        self.script_lines.append(f"{self.directive} {prefix}{name}={value}")

    def add_flag(self, name: str):
        """
        Add a boolean flag (e.g., --exclusive).
        """
        self.script_lines.append(f"{self.directive} --{name}")

    def render(self) -> str:
        """
        Return the complete script as a single string.
        """
        return "\n".join(self.script_lines)
