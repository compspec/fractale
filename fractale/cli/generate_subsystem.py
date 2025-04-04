#!/usr/bin/env python

import os
import sys

from fractale.store import FractaleStore


def main(args, extra, registry):
    """
    Run an extraction. This can be converted to a proper function
    if needed.
    """
    store = FractaleStore(args.config_dir)

    # Discover subsystem plugins
    args.name = args.generate
    plugin = registry.get_plugin(args.generate)

    # Generate / extract based on the plugin type
    # Likely we want to better define these
    attributes = plugin.extract(args, extra)

    # Save to store
    store.save_subsystem(args.cluster, plugin.name, attributes)
