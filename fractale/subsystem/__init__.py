from .subsystem import SubsystemSolver


def get_subsystem_solver(path, backend="database", by_type=None):
    """
    Generate a user subsystem registry, where the structure is expected
    to be a set of <cluster>/<subsystem>. For the FractaleStore, this
    is the store.clusters_root. If by_type is set, we just load one
    subsystem type. This can be extended to handle a list.
    """
    return SubsystemSolver(path, backend, by_type)
