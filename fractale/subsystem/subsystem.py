import os

from rich import print

import fractale.defaults as defaults
import fractale.subsystem.solver as solvers
import fractale.utils as utils


class SubsystemSolver:
    """
    A subsystem solver has (and loads) one or more subsystems.

    It uses a solver backend to answer questions about resource
    (and subsystem) satisfiability. Different backends (e.g.,
    database or memory graph) are provided.
    """

    def __init__(self, path, backend="database", by_type=None):
        self.load_solver(backend, path, by_type=by_type)

        # This is the fractale metadata root with clusters and subsystems
        # We need to store it to provide to select backends
        self.root = path

    def load_solver(self, backend, path, by_type=None):
        """
        Load a backend that drives the Solver.
        """
        if backend not in defaults.solver_backends:
            raise ValueError(
                f"Backend {backend} is not supported. Options are {defaults.solver_backends}"
            )

        # The subsystem registr
        self.backend = solvers.load_solver(backend, path, by_type=by_type)

    def render(self, subsystems):
        """
        Render lines for some subsystem result
        """
        return self.backend.render(subsystems)

    def satisfied(self, jobspec, return_results=False):
        """
        Determine if a jobspec is satisfied by user-space subsystems.
        """
        return self.backend.satisfied(jobspec, return_results)

    def select(self, clusters, algorithm="random"):
        """
        Perform selection based on a chosen algorithm.
        Ideas:

        2. Random: the default
        2. Cost: Give the agent the resource specs, ask for lowest cost.
        3. Time to run: Give the agent queue pending times.
        """
        selected = self.backend.select(self.root, clusters, algorithm)
        print(f'=> Selected cluster(s) "{selected}" using "{algorithm}" algorithm')
        return selected

    def save(self, *args, **kwargs):
        """
        Save a graph (or similar graphical output).
        If not implemented, we hit this.
        """
        self.backend.save(*args, **kwargs)


class Subsystem:
    def __init__(self, filename):
        """
        Load a single subsystem
        """
        # Keep track of total counts of things as a quick proxy
        self.counts = {}
        self.load(filename)

    @property
    def metadata(self):
        return self.data["metadata"]

    @property
    def type(self):
        return self.data["metadata"]["type"]

    def iter_nodes(self):
        """
        General function to iterate over nodes depending on if we
        find JGF v1 (list) or JGF v2 (key value pairs).
        """
        if isinstance(self.graph["nodes"], dict):
            for nid, node in self.graph["nodes"].items():
                yield nid, node
        elif isinstance(self.graph["nodes"], list):
            for node in self.graph["nodes"]:
                yield node["id"], node
        else:
            raise ValueError(f"Unsupported subsystem graph type {type(self.graph['nodes'])}")

    def load(self, filename):
        """
        Load a subsystem file, ensuring it exists.
        """
        # Derive the subsystem name from the filepath
        # /home/vanessa/.fractale/clusters/a/spack/graph.json
        # <root>/clusters/<cluster>/<subsystem>/graph.json
        cluster, subsystem = filename.split(os.sep)[-3:-1]
        print(f'=> Loading cluster "{cluster}" subsystem "{subsystem}"')
        self.data = utils.read_json(filename)

        # The name of the subsystem (not the type). E.g., name "spack" has type "software"
        self.name = subsystem
        self.cluster = cluster

        if "graph" not in self.data:
            raise ValueError(f"Subsystem {subsystem} for cluster {cluster} is missing a graph")

        # Nodes are required (edges are not)
        if "nodes" not in self.graph or not self.graph["nodes"]:
            raise ValueError(f"Subsystem {subsystem} for cluster {cluster} is missing nodes")

        # If the metadata doesn't have a type, we assume containment
        if not self.data.get("metadata", {}).get("type"):

            # Flux JGF doesn't have this extra metadata
            if subsystem == "containment":
                metadata = self.data.get("metadata", {})
                metadata["type"] = "containment"
                self.data["metadata"] = metadata
            else:
                raise ValueError(
                    f"Subsystem {subsystem} for cluster {cluster} is missing a type (metadata->type)"
                )

    @property
    def graph(self):
        """
        Return the graph, which is required to exist and be populated to load.
        """
        return self.data["graph"]
