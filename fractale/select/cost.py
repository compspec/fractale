from fractale.agent.cost import CostAgent


class CostSelection:
    """
    Random selection selects randomly from a list of contenders.
    """

    def select(self, clusters_root, clusters):
        """
        Cost selection can be done for clusers we have node metadata for.
        """
        from fractale.subsystem import get_subsystem_solver

        # The solver here doesn't matter - we just need the metadata
        solver = get_subsystem_solver(clusters_root, by_type="containment")

        # Prepare the prompt. We need to get node and get unique counts of resources.
        # We also need an application running time / name. Let's assume we don't have
        # that and ask for a standard unit.
        for cluster in clusters:
            # TODO why no results? need to look at get_subsystem_nodes
            # STOPPED HERE - we need to find how to query the right metadata.
            # Arguably we should just dump the nodes...
            nodes = solver.backend.get_subsystem_nodes(cluster=cluster)
        print("DO COST SELECTION")
        import IPython

        IPython.embed()
