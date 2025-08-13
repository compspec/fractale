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
from rich.syntax import Syntax

import fractale.agent.kubernetes_job.prompts as prompts
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.errors import DebugAgent

yaml_pattern = r"```(?:yaml)?\n(.*?)```"

# All the ways a container can go wrong... (upside down smiley face)
container_issues = [
    "ImagePullBackOff",
    "ErrImagePull",
    "ErrImageNeverPull",
    "CrashLoopBackOff",
    "CreateContainerConfigError",
]


class KubernetesJobAgent(GeminiAgent):
    """
    A Kubernetes Job agent knows how to design a Kubernetes job.
    """

    name = "kubernetes-job"
    description = "Kubernetes Job agent"

    # Arbitrary max tries for class...
    max_tries = 25

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

    def _run(self, context):
        """
        Run the agent.
        """
        # These are required, context file is not (but recommended)
        context = self.add_build_context(context)

        # This will either generate fresh or rebuild erroneous Job
        job_crd = self.generate_crd(context)
        logger.custom(job_crd, title="[green]job.yaml[/green]", border_style="green")

        # Make and deploy it! Success is exit code 0.
        return_code, output = self.deploy(context)
        if return_code == 0:
            self.print_result(job_crd)
            logger.success(f"Deploy complete in {self.attempts} attempts")
        else:
            logger.error(f"Build failed:\n{output[-1000:]}", title="Deploy Status")
            print("\n[bold cyan] Requesting Correction from Kubernetes Job Agent[/bold cyan]")
            self.attempts += 1

            # Ask the debug agent to better instruct the error message
            context.error_message = output
            agent = DebugAgent()
            # This updates the error message to be the output
            context = agent.run(context, requires=prompts.requires)

            # Return early based on max attempts
            # if self.return_on_failure():
            #    context.return_code = -1
            #    context.result = output
            #    return self.get_result(context)

            # Trigger again, provide initial context and error message
            # This is the internal loop running, no manager agent
            context.result = job_crd
            return self.run(context)

        self.write_file(context, job_crd)
        return context

    def add_build_context(self, context):
        """
        Build context can come from a dockerfile, or context_file.
        """
        # We already have the dockerfile from the build agent as context.
        if "dockerfile" in context:
            return context
        build_context = context.get("context_file")
        if build_context and os.path.exists(build_context):
            context.dockerfile = utils.read_file(build_context)
        return context

    def print_result(self, job_crd):
        """
        Print Job CRD with highlighted Syntax
        """
        highlighted_syntax = Syntax(job_crd, "yaml", theme="monokai", line_numbers=True)
        logger.custom(
            highlighted_syntax, title="Final Kubernetes Job", border_style="green", expand=True
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

    def wait_for_pod_complete(self, pod_name, namespace):
        """
        Wait for a pod to be ready.
        """
        for j in range(self.max_tries):
            pod_status = self.pod_status(pod_name, namespace)
            pod_phase = pod_status.get("phase")

            # Let's assume when we are running the pod is ready for logs.
            # If not, we need to check container statuses too.
            if pod_phase in ["Succeeded", "Failed"]:
                return True

            print(
                f"[dim]Pod '{pod_name}' has status '{pod_phase}'. Waiting... ({j+1}/{self.max_tries})[/dim]"
            )
            time.sleep(2)

        # If we get here, fail and timeout
        print(f"[red]Pod '{pod_name}' never reached completed status, state is unknown[/red]")
        return False

    def pod_status(self, pod_name, namespace):
        """
        Get pod status (subset of info)
        """
        return self.pod_info(pod_name, namespace).get("status", {})

    def pod_info(self, pod_name, namespace):
        """
        Helper function to get pod status
        """
        # 25 x 5 seconds == 10 minutes
        for _ in range(self.max_tries):
            pod_proc = subprocess.run(
                ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if pod_proc.returncode != 0:
                time.sleep(5)
                continue

            return json.loads(pod_proc.stdout)

    def wait_for_pod_ready(self, pod_name, namespace):
        """
        Wait for a pod to be ready.
        """
        for _ in range(self.max_tries):
            pod_status = self.pod_status(pod_name, namespace)
            pod_phase = pod_status.get("phase")

            # Let's assume when we are running the pod is ready for logs.
            # If not, we need to check container statuses too.
            if pod_phase == "Running":
                print(f"[green]Pod '{pod_name}' entered running phase.[/green]")
                return True

            if pod_phase in ["Succeeded", "Failed"]:
                print(
                    f"[yellow]Pod '{pod_name}' entered terminal phase '{pod_phase}' before logging could start.[/yellow]"
                )
                return True

            # If we get here, not ready - sleep and try again.
            print(
                f"[dim]Pod '{pod_name}' has status '{pod_phase}'. Waiting... ({j+1}/{self.max_tries})[/dim]"
            )
            time.sleep(25)

        # If we get here, fail and timeout
        print(f"[red]Pod '{pod_name}' never reached running status, state is unknown[/red]")
        return False

    def wait_for_job(self, job_name, namespace):
        """
        Wait for a job to be active and fail or succeed.
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

    def deploy(self, context):
        """
        Deploy the Kubernetes Job.
        """
        job_crd = context.result
        cleanup = context.get("cleanup", True)

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

        # Assume one container for now, and manually we can easily check
        found_image = containers[0].get("image")
        if found_image != context.container:
            return (
                1,
                f"Generated YAML has incorrect image name {found_image} - it should be {context.container}.",
            )

        deploy_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary deploy context: {deploy_dir}[/dim]")

        # Write the manifest to a temporary directory
        job_manifest_path = os.path.join(deploy_dir, "job.yaml")
        utils.write_file(job_crd, job_manifest_path)
        logger.info(
            f"Attempt {self.attempts} to deploy Kubernetes Job: [bold cyan]{context.container}"
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
        pod_name = None

        # This assumes a backoff / retry of 1, so we aren't doing recreation
        # If it fails once, it fails once and for all.
        # 60 * 5s = 300s (5 minutes!)
        for i in range(60):

            # 1. Check the parent Job's status for a quick terminal state
            job_status = self.get_job_status(job_name, namespace)
            if job_status and job_status.get("succeeded", 0) > 0:
                # The job is done, try to get logs and report success
                print("[green]✅ Job has Succeeded.[/green]")
                break

            # Womp womp
            if job_status.get("failed", 0) > 0:
                logger.error("Job reports Failed.", title="Job Status")
                diagnostics = self.get_diagnostics(job_name, namespace)
                self.cleanup_job(job_name, namespace)
                return (
                    1,
                    f"Job entered failed state. This usually happens after repeated pod failures.\n\n{diagnostics}",
                )

            # 2. If the job isn't terminal, find the pod. It may not exist yet.
            if not pod_name:
                pod_name = self.get_pod_name_for_job(job_name, namespace)

            # 3. If a pod exists, inspect it deeply for fatal errors or readiness.
            if pod_name:
                pod_info = self.pod_info(pod_name, namespace)
                if pod_info:
                    pod_status = pod_info.get("status", {})
                    pod_phase = pod_status.get("phase")

                    # If the pod is running and its containers are ready, we can log.
                    # Note that after we add init containers, this will need tweaking
                    if pod_phase == "Running":
                        container_statuses = pod_status.get("containerStatuses", [])
                        if all(cs.get("ready") for cs in container_statuses):
                            print(f"[green]✅ Pod '{pod_name}' is Ready.[/green]")
                            break

                    # If the pod succeeded already, we can also proceed...
                    if pod_phase == "Succeeded":
                        print(f"[green]✅ Pod '{pod_name}' has Succeeded.[/green]")
                        break

                    # This is important because a pod can be active, but then go into a crashed state
                    container_statuses = pod_status.get("containerStatuses", [])
                    for cs in container_statuses:
                        if cs.get("state", {}).get("waiting"):
                            reason = cs["state"]["waiting"].get("reason")
                            if reason in container_issues:
                                message = cs["state"]["waiting"].get("message")
                                logger.error(
                                    f"Pod has a fatal container status: {reason}", title="Pod Error"
                                )
                                diagnostics = self.get_diagnostics(job_name, namespace)
                                self.cleanup_job(job_name, namespace)
                                return (
                                    1,
                                    f"Pod '{pod_name}' is stuck in a fatal state: {reason}\nMessage: {message}\n\n{diagnostics}",
                                )

                    print(
                        f"[dim]Job is active, Pod '{pod_name}' has status '{pod_phase}'. Waiting... ({i+1}/60)[/dim]"
                    )

                # This means we saw the pod name, but didn't get pod info / it disappeared - let loop continue
                else:
                    print(
                        f"[dim]Job is active, but Pod '{pod_name}' disappeared. Waiting for new pod... ({i+1}/60)[/dim]"
                    )
                    pod_name = None

            # No pod yet, keep waiting.
            else:
                print(f"[dim]Job is active, but no pod found yet. Waiting... ({i+1}/60)[/dim]")

            time.sleep(5)

        # This gets hit when the loop is done, so we probably have a timeout
        else:
            diagnostics = self.get_diagnostics(job_name, namespace)
            return (
                1,
                f"Timeout: Job did not reach a stable running or completed state within the time limit.\n\n{diagnostics}",
            )

        # Let's try to stream logs!
        print("[green]🚀 Proceeding to stream logs...[/green]")
        full_logs = self.get_job_logs(job_name, namespace)

        # Wait for pod to be ready, then we can get logs
        self.wait_for_pod_ready(pod_name, namespace)

        # The above command will wait for the job to complete, so this should be OK to do.
        is_active = True
        while is_active:
            final_status = self.get_job_status(job_name, namespace)
            is_active = final_status.get("active", 0) > 0
            time.sleep(5)

        # But did it succeed?
        if final_status.get("succeeded", 0) > 0:
            print(f"\n[green]✅ Job final status is Succeeded.[/green]")
        else:
            print("\n[red]❌ Job final status is Failed.[/red]")
            diagnostics = self.get_diagnostics(job_name, namespace)
            self.cleanup_job(job_name, namespace)
            # We already have the logs, so we can pass them directly.
            return 1, prompts.failure_message % (diagnostics, full_logs)

        if cleanup and os.path.exists(deploy_dir):
            print(f"[dim]Cleaning up temporary deploy directory: {deploy_dir}[/dim]")
            self.cleanup_job(job_name, namespace)
            shutil.rmtree(deploy_dir, ignore_errors=True)
        return 0, full_logs

    def get_job_logs(self, job_name, namespace):
        """
        Get the logs of a pod.
        """
        full_logs = ""
        # We use the job selector to get logs, which is more robust if the pod was recreated.
        log_cmd = ["kubectl", "logs", "-f", f"job/{job_name}", "-n", namespace]
        with subprocess.Popen(
            log_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        ) as log_process:
            # We can add a timeout to the log streaming itself if needed
            # For now, we wait for it to complete naturally.
            full_logs = "".join(log_process.stdout)
        return full_logs

    def get_job_status(self, job_name, namespace):
        """
        Get job status
        """
        final_status_proc = subprocess.run(
            ["kubectl", "get", "job", job_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        return json.loads(final_status_proc.stdout).get("status", {})

    def get_job_status(self, job_name, namespace):
        """
        Get the job status, return None if not possible.
        """
        job_info = subprocess.run(
            ["kubectl", "get", "job", job_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if job_info.returncode == 0:
            return json.loads(job_info.stdout).get("status", {})

    def generate_crd(self, context):
        """
        Generates or refines an existing Job CRD using the Gemini API.
        """
        prompt = self.get_prompt(context)
        print("Sending generation prompt to Gemini...")
        print(textwrap.indent(prompt, "> ", predicate=lambda _: True))

        content = self.ask_gemini(prompt)
        print("Received response from Gemini...")

        # Try to remove code (Dockerfile, manifest, etc.) from the block
        try:
            content = self.get_code_block(content, "yaml")

            # If we are getting commentary...
            match = re.search(yaml_pattern, content, re.DOTALL)
            if match:
                job_crd = match.group(1).strip()
            else:
                job_crd = content.strip()
            context.result = job_crd
            return job_crd

        except Exception as e:
            sys.exit(f"Error parsing response from Gemini: {e}\n{content}")
