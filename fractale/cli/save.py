#!/usr/bin/env python

import sys

from fractale.store import FractaleStore
from fractale.subsystem import get_subsystem_solver


def main(args, extra, **kwargs):
    """
    Save a cluster and subsystem graph.
    """
    store = FractaleStore(args.config_dir)
    solver = get_subsystem_solver(store.clusters_root, args.solver)
    outfile = args.out
    if not outfile:
        outfile = f"cluster-{args.cluster}-{args.subsystem}-{args.solver}.svg"
    solver.save(args.cluster, args.subsystem, outfile)
