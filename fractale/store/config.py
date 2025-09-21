import os
from pathlib import Path

from rich import print

import fractale.defaults as defaults
import fractale.utils as utils



class FractaleStore:
    """
    A FractaleStore is a metadata root for subsytsems and clusters.
    """

    def __init__(self, config_path=None):
        """
        Generate store home.
        """
        self.root = config_path or self.default_root

    @property
    def default_root(self):
        return os.path.join(Path.home(), defaults.fractale_dir)

    @property
    def clusters_root(self):
        return os.path.join(self.root, "clusters")

    def detect(self):
        """
        Detect subsystems.
        """
        from compspec.plugin.registry import PluginRegistry

        registry = PluginRegistry()
        registry.discover()
        cluster = utils.get_local_cluster()

        for plugin, module in registry.plugins.items():
            # Plugins are not required to implement detection
            if not hasattr(module, "detect"):
                continue
            print(f"Detection for '{plugin}'")

            # A detection is headless extraction
            if module.check():
                graph = module.detect()
                self.save_subsystem(cluster, plugin, graph)

    def save_subsystem(self, cluster_name, plugin_name, graph):
        """
        Save a graph subsystem
        """
        plugin_path = self.cluster_subsystem(cluster_name, plugin_name)
        if not os.path.exists(plugin_path):
            print(f"Creating subsystem graph store for {plugin_name}")
            os.makedirs(plugin_path)
        print(f"Writing subsystem graph store for {plugin_name} to {plugin_path}")
        utils.write_json(graph, os.path.join(plugin_path, "graph.json"))

    def cluster_subsystem(self, cluster, subsystem):
        return os.path.join(self.clusters_root, cluster.lower(), subsystem)
