import os

from .database import DatabaseSolver


def load_solver(backend, path):
    """
    Load the solver backend
    """
    if backend == "database":
        return DatabaseSolver(path)

    raise ValueError(f"Unsupported backend {backend}")
