import copy
import json

from fractale.logger import LogColors
from fractale.logger.generate import JobNamer
from fractale.transformer.base import TransformerBase
from fractale.transformer.flux.validate import Validator


class FluxWorkload(TransformerBase):
    """
    A Flux Transformer is a very manual way to transform a subsystem into
    a batch script. I am not even using jinja templates, I'm just
    parsing the subsystems in a sort of manual way. This a filler,
    and assuming that we will have an LLM that can replace this.
    """

    def parse(self, jobspec):
        """
        Parse an (expected) Flux jobspec. Right now we assume it is from
        the user, so it is a Flux batch script.
        """
        validator = Validator("batch")

        # This is a parsed (normalized) JobSpec
        return validator.parse(jobspec)

    def run(self, matches, jobspec):
        """
        Parse the jobspec into tasks for flux.
        """
        namer = JobNamer()
        # Here we want to group by cluster
        # We need to artificially parse the match metadata
        # This is handled by the solver, because each solver can
        # hold and represent metadata differently.
        for cluster, subsystems in matches.matches.items():

            # There are two strategies we could take here. To update the flux
            # jobscript to have a batch script (more hardened, but doesn't
            # fit the LLM work we are doing) or try to write a flux run command
            # in a batch script (better fits). I don't like either way,
            # but I dislike the second way slightly less.
            script = "#!/bin/bash\n"
            for line in self.solver.render(subsystems):
                script += line

            # Now we add back in the command
            command = " ".join(jobspec["tasks"][0]["command"])
            script += f"\n{command}"

            # This is the task script data
            data = {"mode": 33216, "data": script, "encoding": "utf-8"}

            # I'm going to be careful about updating files
            files = jobspec["attributes"]["system"].get("files") or {}

            # Generate a name for the script
            script_name = namer.generate() + ".sh"
            files[script_name] = data
            jobspec["attributes"]["system"]["files"] = files
            jobspec["tasks"][0]["command"] = ["/bin/bash", f"./{script_name}"]
            yield jobspec

    @property
    def resources(self):
        """
        This returns a global resource lookup
        """
        return self.js.get("resources", {})
