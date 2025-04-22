import json
import os

import fractale.jobspec as jspec
import fractale.utils as utils
from fractale.logger import LogColors, logger
from fractale.subsystem.match import MatchSet


class Solver:
    """
    A solver determines if one or more subsystems for several
    clusters satisfies a resource requirement
    """

    def save(self, *args, **kwargs):
        """
        Save a graph (or similar graphical output).
        If not implemented, we hit this.
        """
        print(f"Save is not supported for {type(self)}")

    def prepare_requirements(self, jobspec):
        """
        Shared function to read in jobspec, add containment requires
        """
        # This handles json or yaml
        js = utils.load_jobspec(jobspec)

        requires = js["attributes"].get("system", {}).get("requires")

        # Special case: containment - these come from resources in the jobspec
        # we can try matching if we have defined containment subsystems
        requires["containment"] = jspec.flatten_jobspec_resources(js)
        return requires

    def render(self, subsystems):
        """
        Take in a set of cluster matches and
        """
        return []

    def satisfied(self, jobspec, return_results=False):
        """
        Determine if a jobspec is satisfied by user-space subsystems.
        """
        requires = self.prepare_requirements(jobspec)

        # These clusters will satisfy the request
        matches = MatchSet()

        # We don't care about the association with tasks - the requires are matching clusters to entire jobs
        # We could optimize this to be fewer queries, but it's likely trivial for now
        for subsystem_type, items in requires.items():

            # Get one or more matching subsystems (top level) for some number of clusters
            # The subsystem type is like the category (e.g., software)
            subsystems = self.get_subsystem_by_type(subsystem_type)
            if not subsystems:
                continue

            # For each subsystem, since we don't have a query syntax developed, we just look for nodes
            # that have matching attributes. Each here is a tuple, (name, cluster, type)
            for subsystem in subsystems:
                name, cluster, subsystem_type = subsystem

                # If subsystem is containment and we don't have enough totals, fail
                if "containment" in self.subsystems:
                    if not self.assess_containment(requires["containment"]):
                        print(f"{LogColors.RED}=> No Matches due to containment{LogColors.ENDC}")
                        return False

                # "Get nodes in subsystem X" if we have a query syntax we could limit to a type, etc.
                # In this case, the subsystem is the name (e.g., spack) since we might have multiple for
                # a type (e.g., software). This returns labels we can associate with attributes.
                # labels = self.get_subsystem_nodes(cluster, name)

                # "Get attribute key values associated with our search. This is done very stupidly now
                nodes = self.find_nodes(cluster, name, items)
                if not nodes:
                    continue
                # This is adding cluster, subsystem name, match criteria, and node ids
                matches.add(cluster, name, items, nodes)

            if matches:
                print(f"\n{LogColors.OKBLUE}({matches.count}) Matches {LogColors.ENDC}")
                for match in matches.iterset():
                    print(f"cluster ({match.cluster}) subsystem ({match.subsystem})")
                if return_results:
                    return matches
                return True
            else:
                print(f"{LogColors.RED}=> No Matches{LogColors.ENDC}")
            return False

    def load(self, path):
        """
        Load a group of subsystem files, typically json JGF.

        We also are careful to store metadata here that might be needed for
        rendering.
        """
        from fractale.subsystem.subsystem import Subsystem

        self.metadata = {}

        if not os.path.exists(path):
            raise ValueError(f"User subsystem directory {path} does not exist.")
        files = utils.recursive_find(path, "graph[.]json")
        if not files:
            raise ValueError(f"There are no cluster subsystems defined under root {path}")
        for filename in files:
            new_subsystem = Subsystem(filename)
            self.load_subsystem(new_subsystem)
            self.metadata[new_subsystem.name] = new_subsystem.metadata
