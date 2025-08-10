import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

import yaml
from rich import print
from rich.panel import Panel
from rich.syntax import Syntax

import fractale.agent.defaults as defaults
import fractale.agent.kubernetes_job.prompts as prompts
import fractale.utils as utils
from fractale.agent.base import Agent
from fractale.agent.context import get_context

yaml_pattern = r"```(?:yaml)?\n(.*?)```"

import google.generativeai as genai


class KubernetesJobAgent(Agent):
    """
    A Kubernetes Job agent knows how to design a Kubernetes job.
    """

    name = "kubernetes-job"
    description = "Kubernetes Job agent"

    def add_arguments(self, subparser):
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
        # Ensure these are namespaced to your plugin
        agent.add_argument(
            "--outfile",
            help="Output file to write Job manifest to (if not specified, only will print)",
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

        # This is just to identify the agent
        agent.add_argument(
            "--agent-name",
            default=self.name,
            dest="agent_name",
        )

    def init(self):
        """
        Init adds the model. Maybe it's shared between executions, not sure.
        """
        model = genai.GenerativeModel("gemini-2.5-pro")
        self.chat = model.start_chat()

    def requires(self):
        """
        Each agent has a requires function to tell the manager what
        they do and what is required in the context to run them.
        """
        return prompts.requires

    def get_prompt(self, context):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)
        error_message = context.get("error_message")

        # If a previous deploy failed, try to regenerate
        if error_message:
            prompt = prompts.get_regenerate_prompt(context)
        else:
            prompt = prompts.get_generate_prompt(context)
        return prompt

    def run(self, context):
        """
        Run the agent.
        """
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        except KeyError:
            sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")

        # Init attempts. Each agent has an internal counter for total attempts
        self.attempts = self.attempts or 0

        # Create or get global context
        context = get_context(context)

        # These are required
        container = context.get("container", required=True)

        # This will either generate fresh or rebuild erroneous Job
        job_crd = self.generate_crd(context)
        print(Panel(job_crd, title="[green]job.yaml[/green]", border_style="green"))

        # Make and deploy it! Success is exit code 0.
        return_code, output = self.deploy(
            job_crd, image_name=container, cleanup=context.get("cleanup")
        )
        if return_code == 0:
            print(
                Panel(
                    f"[bold green]✅ Deploy complete in {self.attempts} attempts[/bold green]",
                    title="Success",
                    border_style="green",
                )
            )
        else:
            print(
                Panel(
                    "[bold red]❌ Deploy failed[/bold red]",
                    title="Deploy Status",
                    border_style="red",
                )
            )
            print("\n[bold cyan] Requesting Correction from Kubernetes Job Agent[/bold cyan]")
            self.attempts += 1

            # Trigger again, provide initial context and error message
            context.error_message = output
            context.job_crd = job_crd
            return self.run(context)

        self.write_file(context, job_crd)
        self.print_crd(job_crd)
        if context.get("managed") is True:
            return context
        return job_crd

    def print_crd(self, job_crd):
        """
        Print Job CRD with highlighted Syntax
        """
        highlighted_syntax = Syntax(job_crd, "yaml", theme="monokai", line_numbers=True)
        print(
            Panel(
                highlighted_syntax,
                title="[bold green]✅ Final Kubernetes Job[/bold green]",
                border_style="green",
                expand=True,
            )
        )

    def get_diagnostics(self, job_name, namespace):
        """
        Helper to collect rich error data for a failed job.
        """
        print("[yellow]Gathering diagnostics for failed job...[/yellow]")

        describe_job_cmd = ["kubectl", "describe", "job", job_name, "-n", namespace]
        job_description = subprocess.run(
            describe_job_cmd, capture_output=True, text=True, check=False
        ).stdout

        describe_pods_cmd = [
            "kubectl",
            "describe",
            "pod",
            "-l",
            f"job-name={job_name}",
            "-n",
            namespace,
        ]
        pods_description = subprocess.run(
            describe_pods_cmd, capture_output=True, text=True, check=False
        ).stdout

        get_events_cmd = ["kubectl", "get", "events", "-n", namespace, "--sort-by=lastTimestamp"]
        events = subprocess.run(get_events_cmd, capture_output=True, text=True, check=False).stdout
        return prompts.meta_bundle % (job_description, pods_description, events)

    def wait_for_pod_ready(self, pod_name, namespace):
        """
        Wait for a pod to be ready.
        """
        # Wait ~10 minutes to be ready
        max_tries = 25
        for j in range(max_tries):
            pod_proc = subprocess.run(
                ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if pod_proc.returncode != 0:
                time.sleep(5)
                continue

            pod_status = json.loads(pod_proc.stdout).get("status", {})
            pod_phase = pod_status.get("phase")

            # Let's assume when we are running the pod is ready for logs.
            # If not, we need to check container statuses too.
            if pod_phase == "Running":
                print(f"[green]Pod '{pod_name}' entered running phase.[/green]")
                return True
            elif pod_phase in ["Succeeded", "Failed"]:
                print(
                    f"[yellow]Pod '{pod_name}' entered terminal phase '{pod_phase}' before logging could start.[/yellow]"
                )
                return True

            print(
                f"[dim]Pod '{pod_name}' has status '{pod_phase}'. Waiting... ({j+1}/{max_tries})[/dim]"
            )
            time.sleep(25)

        # If we get here, fail and timeout
        print(f"[red]Pod '{pod_name}' never reached running status, state is unknown[/red]")
        return False

    def wait_for_job(self, job_name, namespace):
        """
        Wait for a job to be active - fail / succeed / go on vacation, etc.
        """
        is_active, is_failed, is_succeeded = False, False, False

        # Poll for 10 minutes. This assumes a large container that needs to pull
        for i in range(60):  # 60 * 10s = 600s = 10 minutes
            get_status_cmd = ["kubectl", "get", "job", job_name, "-n", namespace, "-o", "json"]
            status_process = subprocess.run(
                get_status_cmd, capture_output=True, text=True, check=False
            )
            if status_process.returncode != 0:
                time.sleep(10)
                continue

            status = json.loads(status_process.stdout).get("status", {})
            if status.get("succeeded", 0) > 0:
                print("[green]✅ Job succeeded before log streaming began.[/green]")
                is_succeeded = True
                break

            if status.get("failed", 0) > 0:
                print("[red]❌ Job entered failed state.[/red]")
                is_failed = True
                break

            if status.get("active", 0) > 0:
                print("[green]Job is active. Attaching to logs...[/green]")
                is_active = True
                break

            print(f"[dim]Still waiting... ({i+1}/30)[/dim]")
            time.sleep(10)
        return is_active, is_failed, is_succeeded

    def get_pod_name_for_job(self, job_name, namespace):
        """
        Find the name of the pod created by a specific job.
        """
        cmd = [
            "kubectl",
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"job-name={job_name}",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.stdout.strip() or None

    def cleanup_job(self, job_name, namespace):
        """
        Delete job so we can create again.
        """
        subprocess.run(
            ["kubectl", "delete", "job", job_name, "-n", namespace, "--ignore-not-found"],
            capture_output=True,
            check=False,
        )

    def deploy(self, job_crd, image_name, cleanup=True):
        """
        Deploy the Kubernetes Job.
        """
        # Not sure if this can happen, assume it can
        if not job_crd:
            raise ValueError("No Job Specification content provided.")

        # Job needs to load as yaml to work, period.
        try:
            job_data = yaml.safe_load(job_crd)
        except Exception as e:
            return (1, str(e) + "\n" + job_crd)

        # Cut out early if we don't have a known name.
        job_name = job_data.get("metadata", {}).get("name")
        namespace = job_data.get("metadata", {}).get("namespace", "default")
        if not job_name:
            return (1, f"Generated YAML is missing required '.metadata.name' field.")

        # If it doesn't follow instructions...
        containers = (
            job_data.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or []
        )
        if not containers:
            return (
                1,
                "Generated YAML is missing required '.spec.template.spec.containers' list field.",
            )

        # Assume one container for now
        found_image = containers[0].get("image")
        if found_image != image_name:
            return (
                1,
                "Generated YAML has incorrect image name {found_image} - it should be {image_name}.",
            )

        deploy_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary deploy context: {deploy_dir}[/dim]")

        # Write the manifest to a temporary directory
        job_manifest_path = os.path.join(deploy_dir, "job.yaml")
        utils.write_file(job_crd, job_manifest_path)
        print(
            Panel(
                f"Attempt {self.attempts+1} to deploy Kubernetes Job: [bold cyan]{image_name}[/bold cyan]",
                title="[blue]Kubernetes Job[/blue]",
                border_style="blue",
            )
        )

        # 1. First check if the kubectl apply command worked
        apply_cmd = ["kubectl", "apply", "-f", job_manifest_path]
        apply_process = subprocess.run(
            apply_cmd, capture_output=True, text=True, check=False, cwd=deploy_dir
        )

        if apply_process.returncode != 0:
            print("[red]'kubectl apply' failed. The manifest is likely invalid.[/red]")
            return (apply_process.returncode, apply_process.stdout + apply_process.stderr)

        print("[green]✅ Manifest applied successfully.[/green]")

        # 2. We then need to wait until the job is running or fails
        print("[yellow]Waiting for Job to start... (Timeout: 5 minutes)[/yellow]")
        is_active, is_failed, is_succeeded = self.wait_for_job(job_name, namespace)

        # 3. If the job status goes into an erroneous state, capture all the output.
        if is_failed or not (is_active or is_succeeded):
            error_reason = "Job failed." if is_failed else "Job timed out waiting to start."
            diagnostics = self.get_diagnostics(job_name, namespace)
            self.cleanup_job(job_name, namespace)
            return (1, f"{error_reason}\n\n{diagnostics}")

        # 4. If the job starts to run, capture the logs until the end.
        if is_active:

            # Get a representative pod for the job
            pod_name = None
            while not pod_name:
                pod_name = self.get_pod_name_for_job(job_name, namespace)
                time.sleep(5)

            # Wait for the job to be ready (before we ask for logs)
            is_ready = self.wait_for_pod_ready(pod_name, namespace)
            if not is_ready:
                diagnostics = self.get_diagnostics(job_name, namespace)
                error_reason = "Job never reached Running, Succeeded, or Failed state."
                return (1, diagnostics + "\n" + error_reason)

            log_cmd = ["kubectl", "logs", "-f", f"job/{job_name}", "-n", namespace]
            with subprocess.Popen(
                log_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            ) as log_process:
                # Capture logs as they stream for the final error report if needed
                # I'm trying this instead of the log streamer - we will see.
                full_logs = "".join(log_process.stdout)

            # Final check to see if it succeeded or failed after running
            final_status_proc = subprocess.run(
                ["kubectl", "get", "job", job_name, "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            final_status = json.loads(final_status_proc.stdout).get("status", {})

            # But did it succeed?
            if final_status.get("succeeded", 0) > 0:
                print("[green]✅ Job completed successfully after running.[/green]")
            else:
                print("[red]Job failed during execution.[/red]")
                diagnostics = self.get_diagnostics(job_name, namespace)
                self.cleanup_job(job_name, namespace)
                return (1, prompts.failure_message % (full_logs, diagnostics))

        if cleanup is not False:
            self.cleanup_job(job_name, namespace)
        print(f"[dim]Cleaning up temporary deploy directory: {deploy_dir}[/dim]")
        shutil.rmtree(deploy_dir, ignore_errors=True)
        return (0, "Success")

    def generate_crd(self, context, template=None):
        """
        Generates or refines an existing Job CRD using the Gemini API.
        """
        prompt = self.get_prompt(context)
        print("Sending generation prompt to Gemini...")
        print(textwrap.indent(prompt, "> ", predicate=lambda _: True))

        response = self.ask_gemini(prompt)
        print("Received response from Gemini...")

        # Try to remove Dockerfile from code block
        try:
            content = response.text.strip()
            if content.startswith("```yaml"):
                content = content[len("```yaml") :]
            if content.startswith("```"):
                content = content[len("```") :]
            if content.endswith("```"):
                content = content[: -len("```")]

            # If we are getting commentary...
            match = re.search(yaml_pattern, content, re.DOTALL)
            if match:
                job_crd = match.group(1).strip()
            else:
                job_crd = content.strip()
            context.result = job_crd
            return job_crd

        except Exception as e:
            sys.exit(f"Error parsing response from Gemini: {e}\n{response.text}")
