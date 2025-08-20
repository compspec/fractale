import argparse
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