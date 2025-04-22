import graph_tool.all as gt

import fractale.jobspec as jspec
from fractale.logger import LogColors
from fractale.subsystem.match import MatchSet

from .base import Solver

node_properties = [
    "type",
    "id",
    "basename",
    "label",
    "name",
    "subsystem",
    "cluster",
    "subsystem-type",
]


class GraphSolver(Solver):
    """
    A graph solver solves for a cluster by traversing a graph.
    """

    def __init__(self, path):
        self.subsystems = {}
        self.clusters = set()
        self.vertices = {}
        self.create_graph()
        self.load(path)

    def create_graph(self):
        """
        Create graph for subsytems, nodes, edges.
        """
        self.g = gt.Graph(directed=True)

        # The type will be node, cluster, socket, core, etc.
        # The id will be the identifier, e.g., node0, core0, etc.
        for name in node_properties:
            self.g.vertex_properties[name] = self.g.new_vertex_property("string")

    def load_subsystem(self, subsystem):
        """
        Load a new subsystem to the memory graph (backed by C++ and boost)!
        """
        self.clusters.add(subsystem.cluster)

        # Determine if we've seen the subsystem - we can't add it again
        # In practice this should not happen
        subsystems_known = self.subsystems.get(subsystem.cluster) or {}
        if subsystem.name in subsystems_known:
            raise ValueError(f"Subsystem {subsystem.name} was already added to {subsystem.cluster}")

        # Keep global count of different resource types
        counts = {}

        # Get handles for properties for easiest access
        props = self.g.vertex_properties

        # Keep a lookup of nodes based on the id to create edges
        node_lookup = {}

        # First create all nodes.
        for _, node in subsystem.iter_nodes():

            # Create the node vertex, add properties
            node_v = self.g.add_vertex()
            typ = node["metadata"]["type"]

            # Flux containment has an id at the top level, compspec uses id in metadata
            node_id = node.get("id") or node["metadata"]["id"]

            # This needs to be a lookup across subsystems
            global_id = f"{subsystem.cluster}-{subsystem.name}-{node_id}"

            # Update all properties
            props["cluster"][node_v] = subsystem.cluster
            props["subsystem"][node_v] = subsystem.name
            props["subsystem-type"][node_v] = subsystem.type
            props["type"][node_v] = typ
            props["name"][node_v] = node["metadata"]["name"]
            props["basename"][node_v] = node["metadata"]["basename"]
            props["id"][node_v] = global_id

            # Add attributes, arbitrary key value pair metadata
            # TODO, choose property type based on Python type?
            for key, value in node["metadata"].get("attributes", {}).items():
                if key not in props:
                    props[key] = self.g.new_vertex_property("string")
                props[key][node_v] = value

            # Add the node to the lookup
            node_lookup[node_id] = node_v
            self.vertices[global_id] = node_v

            if typ not in counts:
                counts[typ] = 0
            counts[typ] += 1

        # We only need to add edges for containment subsystem, for now
        # We don't have a use case for others
        if subsystem.name == "containment":
            for edgeset in subsystem.graph.get("edges") or []:
                src = edgeset["source"]
                target = edgeset["target"]
                self.g.add_edge(node_lookup[src], node_lookup[target])

        # Update properties and counts
        for key, value in props.items():
            self.g.vertex_properties[key] = value
        subsystems_known[subsystem.name] = counts
        self.subsystems[subsystem.cluster] = subsystems_known

    def save(self, cluster, subsystem, outpath):
        """
        Custom function to save a view of the graph
        """
        cluster_filter = self.g.new_vertex_property("bool", val=False)
        for v in self.g.vertices():
            if (
                self.g.vertex_properties["cluster"][v] == cluster
                and self.g.vertex_properties["subsystem"][v] == subsystem
            ):
                cluster_filter[v] = True
        view = gt.GraphView(self.g, vfilt=cluster_filter)

        # Assume people do sane things with file extensions
        fmt = outpath.rsplit(".")[-1].lower()
        print(f'{LogColors.OKBLUE}Saving to "{outpath}"{LogColors.ENDC}')
        gt.graph_draw(view, output=outpath, fmt=fmt)

    def satisfied(self, jobspec, return_results=False):
        """
        Determine if a jobspec is satisfied by user-space subsystems.
        """
        requires = self.prepare_requirements(jobspec)

        # First get cluster contenders based on subsystem requirements
        # Note we are passing in a list so we get it back :)
        is_satisfied, matches = self.check_subsystem_satisfies(requires)
        if not is_satisfied:
            return MatchSet()

        # Extract slot resources
        # Flux jobspecs should only have one slot (there is only one task allowed).
        slot = jspec.extract_slot(jobspec)
        if not slot:
            raise ValueError("Did not find slot in jobspec.")
        slot = slot[0]

        # Now we do graph stuff. Let's create a graph view that just includes the clusters
        # This will be greedy - we will stop when we find the first match
        for cluster in matches.clusters:
            if self.check_cluster_satisfies(cluster, slot):
                print(f'{LogColors.OKBLUE}Cluster "{cluster}" is a match{LogColors.ENDC}')
            else:
                matches.remove(cluster)

        if matches.count == 0:
            print(f"{LogColors.RED}=> No Matches{LogColors.ENDC}")
            return False
        if return_results:
            return matches
        return True

    def check_cluster_satisfies(self, cluster, slot):
        """
        Given a cluster name, check if it satifies the containment subsystem,
        which is provided via a slot.
        """
        print(
            f'    {LogColors.PURPLE}=> Exploring cluster "{cluster}" containment subsystem{LogColors.ENDC}'
        )

        # Strategy:
        # 1. Create a view of the graph with just the cluster
        # 2. For that view, also filter down to nodes to explore
        # We can't filter to just nodes, we would lose edges to other types
        cluster_filter = self.g.new_vertex_property("bool", val=False)

        # These will be nodes to start at
        node_vertices = []
        for v in self.g.vertices():
            if self.g.vertex_properties["cluster"][v] == cluster:
                cluster_filter[v] = True

                # Is this vertex additionally a node?
                if self.g.vertex_properties["type"][v] == "node":
                    node_vertices.append(v)

        # This is a view of the entire graph of just nodes
        view = gt.GraphView(self.g, vfilt=cluster_filter)

        # Let's traverse! Ee will be greedy and stop when we get the required slots
        # Also keep count of the number of slots we found
        visited = set()
        slots_found = 0

        # Explore until we fill the required slot
        for vertex in node_vertices:
            if vertex in visited:
                continue
            visited.add(vertex)

            # Keep exploring until we find the slot! We only have one edge type, so
            # just immediately look at the current vertex, then neighbors (and not edges)
            to_explore = [vertex]
            while to_explore:
                # Pop from the end, so we get the last added
                contender = to_explore.pop()

                # This is the type of vertex (e.g., core, node). Does it match the slot?
                v_type = view.vp.type[contender]

                # This means we found the type that satisfies a slot.
                # We need to explore it fully for resources asked for and determine if it's good.
                if v_type == slot.start_type:
                    if self.explore_slot(contender, slot):
                        slots_found += 1

                        # This cluster is a match
                        if slots_found == slot.total:
                            return True

                # Keep exploring looking for slots
                else:
                    to_explore += list(contender.out_neighbors())
        return False

    def explore_slot(self, vertex, slot):
        """
        Evaluate a vertex (and children) for satisfying a slot.
        """
        to_explore = [vertex]

        # Keep track of slot counts we find. The traversal with enforce order

        # This creates a temporary view of the slot we can change
        with slot.evaluate() as evaluator:

            # These are requirements (an interable)
            requires = evaluator.next_requirement()
            requires_type, requires_count = next(requires)

            # Look through vertices. DFS means we go down before we explore more.
            while to_explore:
                vertex = to_explore.pop(0)
                v_type = self.g.vp.type[vertex]

                # This means we are satisfying the slot, keep going through requires
                # We assume one vertex == a count of 1. There is a size attribute but
                # I'm not sure it is used in practice.
                if v_type == requires_type:
                    to_explore += list(vertex.out_neighbors())

                    # Tell the evaluator we found the resource type (not sure I like this name)
                    # If this returns true, we have reached the total we need.
                    if evaluator.found(v_type, 1, requires_count):
                        current_count = evaluator.count(v_type)
                        status = f"   {LogColors.PURPLE}({requires_count}/{current_count}) {LogColors.ENDC}".rjust(
                            25
                        )
                        print(
                            status
                            + f"{LogColors.OKCYAN}satisfied resource {v_type} {LogColors.ENDC}"
                        )

                        # Keep going until we have no more.
                        try:
                            requires_type, requires_count = next(requires)
                        except StopIteration:
                            break
                    else:
                        current_count = evaluator.count(v_type)
                        status = f"   {LogColors.PURPLE}({current_count}/{requires_count}) {LogColors.ENDC}".rjust(
                            25
                        )
                        print(
                            status + f"{LogColors.OKCYAN}found resource {v_type} {LogColors.ENDC}"
                        )

                # For now, we assume this is a failure, because
                # the slot doesn't have the resource type we need
                else:
                    return False

            # Is the evaluator satisfied
            return evaluator.satisfied()

        # We should not get here
        return False

    def render(self, subsystems):
        """
        Yield lines for the transformer.
        """
        for subsystem, items in subsystems.items():
            for item in items:

                # Spack needs a spack load. The "right" way to do this would be
                # to get the initial node back from the solver. But I'm too lazy
                # right now for that, especially if this is just a demo
                for v_id in item.details:
                    v = self.vertices[v_id]
                    item_type = self.g.vp["type"][v]
                    item_name = self.g.vp["name"][v]

                    # Spack template
                    if subsystem == "spack" and item_type == "package" and item_name is not None:
                        yield f"\nspack load {item_name}"

                    # Environment modules template
                    elif (
                        subsystem == "environment-modules"
                        and item_type == "module"
                        and item_name is not None
                    ):
                        yield f"\nmodule load {item_name}"

    def check_subsystem_satisfies(self, requires):
        """
        Determine if subsystems (that are not containment) are satisfied. Unlike a graph
        traversal, since this is based on properties we are doing dumb loop queries.
        Dumb programmer, dumb algorithms, what can I say.
        """
        # Keep track of matching clusters. For this strategy, since we evaluate valuesets for each
        # subsystem, we can only consider a requirement fully satisfied when all valuesets are.
        matches = MatchSet()
        contenders = None

        # Subsystem requirements first
        # Note that these subsystems aren't like spack, modules, etc., they are "software" and more general.
        for subsystem, values in requires.items():
            if subsystem == "containment":
                continue

            # We need to keep track of vertices satisfied (for each valueset)
            satisfied_sets = []

            # Keep track of solutions to send back
            # Each valueset is a set of requirements for a node - we assume number is small
            # All requirements (multiple subsystems, for example) must be met for a single cluster.
            for valueset in values:
                # Within a valueset (a dict of properties that must apply to one node)
                # we need to have overlapping vertices. This is stupid and inefficient, but it
                vertices_satisfied = None

                # Assemble the single query for one or more nodes
                for key, value in valueset.items():
                    # Node properties are directly on the node, not under metadata or attributes
                    if key in node_properties:
                        v_prop = self.g.vertex_properties.get(key)
                    else:
                        v_prop = self.g.vertex_properties.get(f"attribute.{key}")
                    if not v_prop:
                        print(
                            f'{LogColors.RED}=> No Matches due to unknown property "{key}{LogColors.ENDC}"'
                        )
                        return False, matches

                    # Do we have matching vertices anywhere in the graph?
                    vertices = gt.find_vertex(self.g, v_prop, value)
                    if not vertices:
                        print(
                            f'{LogColors.RED}=> No Matches due to missing requirement "{key}={value}"{LogColors.ENDC}'
                        )
                        return False, matches

                    # If we get here, we have vertices. We need to consider vertex and cluster overlap
                    if vertices_satisfied is None:
                        vertices_satisfied = set(vertices)
                    else:
                        # If the current vertices we have don't intersect, we can't satisfy
                        if not vertices_satisfied.intersection(vertices):
                            print(
                                f"{LogColors.RED}=> No Matches due to missing requirement {key}={value}{LogColors.ENDC}"
                            )
                            return False, matches

                        # If we get here, there was an intersection, so add it
                        [
                            vertices_satisfied.add(v)
                            for v in vertices_satisfied.intersection(vertices)
                        ]

                    # Now the same for clusters.
                    # If we haven't defined contenders yet, all here are considered.
                    if contenders is None:
                        contenders = {
                            self.g.vertex_properties["cluster"][v] for v in vertices_satisfied
                        }

                    # If we already have contenders:
                    # 1. Overlap means common nodes (are match vertices are still good)
                    # 2. No overlap - we can't consider cluster because there is a requirement not satisfied
                    else:
                        new_contenders = {
                            self.g.vertex_properties["cluster"][v] for v in vertices_satisfied
                        }
                        if not contenders.intersection(new_contenders):
                            print(
                                f"{LogColors.RED}=> No Matches due to no cluster overlap for {valueset}{LogColors.ENDC}"
                            )
                            return False, matches

                        # If we get here, we still have contender clusters
                        [contenders.add(c) for c in contenders.intersection(new_contenders)]
                        satisfied_sets.append([valueset, vertices_satisfied])

            # If we make it here, we've satisfied all valuesets for a subsystem
            for satisfied_set in satisfied_sets:
                items = []
                for v in satisfied_set[1]:
                    items.append(self.g.vp["id"][v])
                # This is adding cluster, subsystem, valueset, and a list of vertex id
                matches.add(
                    self.g.vp["cluster"][v], self.g.vp["subsystem"][v], satisfied_set[0], items
                )

        # One final check
        if matches.count == 0:
            print(
                f"{LogColors.RED}=> No Matches for any cluster for subsystem requirements{LogColors.ENDC}"
            )
            return False, contenders
        return True, matches
