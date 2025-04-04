#!/usr/bin/env python

import sys

from fractale.store import FractaleStore
from fractale.subsystem import get_subsystem_registry


def main(args, extra, **kwargs):
    """
    Determine if a jobspec can be satisfied by local resources.
    This is a fairly simple (flat) check.
    """
    store = FractaleStore(args.config_dir)
    registry = get_subsystem_registry(store.clusters_root)
    is_satisfied = registry.satisfied(args.jobspec)
    sys.exit(0 if is_satisfied else -1)
