import os

from .database import DatabaseSolver

# Don't require graph_tool
try:
    from .graph import GraphSolver
except ImportError:
    GraphSolver = None


def load_solver(backend, path):
    """
    Load the solver backend
    """
    if backend == "database":
        return DatabaseSolver(path)
    if backend == "graph" and GraphSolver is not None:
        return GraphSolver(path)

    raise ValueError(f"Unsupported backend {backend}")
