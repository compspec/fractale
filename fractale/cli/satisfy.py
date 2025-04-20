#!/usr/bin/env python

import sys

from fractale.store import FractaleStore
from fractale.subsystem import get_subsystem_solver


def main(args, extra, **kwargs):
    """
    Determine if a jobspec can be satisfied by local resources.
    This is a fairly simple (flat) check.
    """
    store = FractaleStore(args.config_dir)
    solver = get_subsystem_solver(store.clusters_root, args.backend)
    is_satisfied = solver.satisfied(args.jobspec)
    sys.exit(0 if is_satisfied else -1)
