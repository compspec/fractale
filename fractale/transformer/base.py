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

    def __init__(self, selector, solver):
        """
        Create a new transformer backend, accepting any options type.

        Validation of transformers is done by the registry
        """
        self.selector = get_selector(selector)
        self.solver = solver

    def parse(self, *args, **kwargs):
        """
        Parse converts the native jobspec to the standard JobSpec
        """
        raise NotImplementedError

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
