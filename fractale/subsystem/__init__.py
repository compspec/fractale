import os

from .subsystem import SubsystemSolver


def get_subsystem_solver(path, backend="database"):
    """
    Generate a user subsystem registry, where the structure is expected
    to be a set of <cluster>/<subsystem>. For the FractaleStore, this
    is the store.clusters_root.
    """
    if not os.path.exists(path):
        raise ValueError(f"Cluster subsystem root {path} does not exist")

    # Generate the subsystem registry
    return SubsystemSolver(path, backend)
