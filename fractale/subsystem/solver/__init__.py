from .database import DatabaseSolver

# Don't require graph_tool
try:
    from .graph import GraphSolver
except ImportError:
    GraphSolver = None


def load_solver(backend, path, by_type=None):
    """
    Load the solver backend
    """
    if backend == "database":
        return DatabaseSolver(path, by_type=by_type)
    if backend == "graph" and GraphSolver is not None:
        return GraphSolver(path, by_type=by_type)

    raise ValueError(f"Unsupported backend {backend}")
