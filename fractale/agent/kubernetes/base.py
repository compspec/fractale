import argparse
import json
import subprocess

from rich import print
from rich.panel import Panel
from rich.syntax import Syntax

import fractale.agent.logger as logger
from fractale.agent.base import GeminiAgent


class KubernetesAgent(GeminiAgent):
    """
    A Kubernetes agent is a base class for a generic Kubernetes agent.
    """

    def _add_arguments(self, subparser):
        """
        Add arguments for the plugin to show up in argparse
        """
        agent = subparser.add_parser(
            self.name,
            formatter_class=argparse.RawTextHelpFormatter,
            description=self.description,
        )
        agent.add_argument(
            "container",
            help="Container unique resource identifier to use (required)",
        )
        agent.add_argument(
            "--environment",
            help="Environment description to build for (defaults to generic)",
        )
        agent.add_argument(
            "--no-pull",
            default=False,
            action="store_true",
            help="Do not pull the image, assume pull policy is Never",
        )
        agent.add_argument("--context-file", help="Context from a deploy failure or similar.")
        return agent

    def print_result(self, job_crd):
        """
        Print Job CRD with highlighted Syntax
        """
        highlighted_syntax = Syntax(job_crd, "yaml", theme="monokai", line_numbers=True)
        logger.custom(
            highlighted_syntax, title="Final Kubernetes Job", border_style="green", expand=True
        )

    def save_log(self, full_logs):
        """
        Save logs to metadata
        """
        if self.save_incremental:
            if "logs" not in self.metadata["assets"]:
                self.metadata["assets"]["logs"] = []
            self.metadata["assets"]["logs"].append({"item": full_logs, "attempt": self.attempts})

    def save_job_manifest(self, job):
        """
        Save job manifest to metadata
        """
        if self.save_incremental:
            if self.result_type not in self.metadata["assets"]:
                self.metadata["assets"][self.result_type] = []
            self.metadata["assets"][self.result_type].append(
                {"item": job, "attempt": self.attempts}
            )

    def cluster_resources(self):
        """
        Get cluster resources - count of nodes and resources.
        I was thinking of caching this, but clusters can change,
        and it's easy (and inexpensive) enough to query that we repeat.
        """
        print("[yellow]Querying Kubernetes cluster for node resources...[/yellow]")
        try:
            # Execute the kubectl command
            result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "json"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            # Parse the JSON output
            nodes_data = json.loads(result.stdout)
            nodes = nodes_data.get("items", [])

            if not nodes:
                print("[red]Error: No nodes found in the cluster.[/red]")
                return None

            # Keep a listing (with count) of node specs
            # The key is the cpu, memory, and arch, and then node count
            node_specs = {}
            for node in nodes:
                node_spec = (
                    node["status"]["allocatable"]["cpu"],
                    node["status"]["allocatable"]["memory"],
                    node["status"]["nodeInfo"]["architecture"],
                )
                if node_spec not in node_specs:
                    node_specs[node_spec] = 0
                node_specs[node_spec] += 1

            # Ensure we expand the resources
            node_specs = [
                {"cpu": x[0], "memory": x[1], "arch": x[2], "count": v}
                for x, v in node_specs.items()
            ]
            cluster_info = {"total_nodes": len(nodes), "node_specs": node_specs}

            print("[green]✅ Successfully retrieved cluster information.[/green]")
            return cluster_info

        except Exception as e:
            print(
                f"[bold red]Error executing kubectl command. Do you have access to the cluster?[/bold red]"
            )
            print(f"Stderr: {e.stderr}")
