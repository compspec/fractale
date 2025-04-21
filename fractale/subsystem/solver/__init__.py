import os

from .database import DatabaseSolver
from .graph import GraphSolver


def load_solver(backend, path):
    """
    Load the solver backend
    """
    if backend == "database":
        return DatabaseSolver(path)
    if backend == "graph":
        return GraphSolver(path)

    raise ValueError(f"Unsupported backend {backend}")
