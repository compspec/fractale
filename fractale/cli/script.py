#!/usr/bin/env python

import json
import sys

from rich import print, print_json
from rich.json import JSON
from rich.pretty import pprint

from fractale.store import FractaleStore
from fractale.subsystem import get_subsystem_solver
from fractale.transformer import get_transformer


def main(args, extra, **kwargs):
    """
    Save a cluster and subsystem graph.
    """
    store = FractaleStore(args.config_dir)

    # Prepare selector and transformer
    solver = get_subsystem_solver(store.clusters_root, args.solver)
    # This is probably overloaded, but we need to be able to look up
    # the templating logic for a subsystem
    transformer = get_transformer(args.transformer, args.selector, solver)
    matches = solver.satisfied(args.jobspec, return_results=True)
    if matches.count == 0:
        sys.exit(-1)

    # Select the results to generate. This consolidates matches (which might include different nodes)
    # into clusters and groups of subsystems
    for script in transformer.render(matches, args.jobspec):
        # Generate batch script or jobspec and print
        pprint(script)
