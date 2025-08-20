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

import fractale.agent.kubernetes.objects as objects
from fractale.agent.kubernetes.base import KubernetesAgent
import fractale.agent.kubernetes.job.prompts as prompts
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.base import GeminiAgent
from fractale.agent.context import get_context
from fractale.agent.decorators import timed
from fractale.agent.errors import DebugAgent


class KubernetesJobAgent(KubernetesAgent):
    """
    A Kubernetes Job agent knows how to design a Kubernetes job.
    """

    name = "kubernetes-job"
    description = "Kubernetes Job agent"
    result_type = "kubernetes-job-manifest"

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

    @timed
    def run_step(self, context):
        """
        Run the agent.
        """
        # These are required, context file is not (but recommended)
        context = self.add_build_context(context)

        # This will either generate fresh or rebuild erroneous Job
        job_crd = self.generate_job_manifest(context)
        logger.custom(job_crd, title="[green]job.yaml[/green]", border_style="green")

        # Make and deploy it! Success is exit code 0.
        return_code, output = self.deploy(context)
        if return_code == 0:
            self.print_result(job_crd)
            logger.success(f"Deploy complete in {self.attempts} attempts")
        else:
            logger.error(f"Deploy failed:\n{output[-1000:]}", title="Deploy Status")
            print("\n[bold cyan] Requesting Correction from Kubernetes Job Agent[/bold cyan]")

            # Ask the debug agent to better instruct the error message
            context.error_message = output

            # This updates the error message to be the output
            context = DebugAgent().run(context, requires=prompts.requires)

            # Return early based on max attempts
            if self.reached_max_attempts() or context.get("return_to_manager") is True:
                context.return_to_manager = False

                # If we are being managed, return the result
                if context.is_managed():
                    context.return_code = -1
                    context.result = context.error_message
                    return context

                # Otherwise this is a failure state
                logger.exit(f"Max attempts {self.max_attempts} reached.", title="Agent Failure")

            self.attempts += 1

            # Trigger again, provide initial context and error message
            # This is the internal loop running, no manager agent
            context.result = job_crd
            return self.run_step(context)

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

    def get_diagnostics(self, job, pod):
        """
        Helper to collect rich error data for a failed job.
        """
        print("[yellow]Gathering diagnostics for failed job...[/yellow]")
        pod_status = pod.get_filtered_status()
        job_status = job.get_filtered_status()

        # Use json.dumps because it's more compact (maybe fewer tokens)
        pod_events = pod.get_events()
        job_events = job.get_events()
        events = sorted(job_events + pod_events, key=lambda e: e.get("lastTimestamp", ""))
        job_description = json.dumps(job_status)
        pods_description = json.dumps(pod_status)
        events_description = json.dumps(events)
        full_logs = job.get_logs()

        # Get job and pod events, add lgs if we have them.
        diagnostics = prompts.meta_bundle % (job_description, pods_description, events_description)
        if full_logs:
            return diagnostics + full_logs
        return diagnostics

    @timed
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
            return 1, "Generated YAML is missing required '.metadata.name' field."

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

        # The debugger can decide to give the user an interactive session
        # For interactive, we set the command to sleep infinity
        if context.get("interactive") is True:
            logger.info(
                f"Starting Interative Debugging Session: job manifest at => {job_manifest_path}\nType 'exit' when done."
            )
            command = job_data["spec"]["template"]["spec"]["containers"][0]["command"]
            logger.custom(f"  Initial command: {command}")
            job_data["spec"]["template"]["spec"]["containers"][0]["command"] = ["sleep", "infinity"]
            job_crd = yaml.dump(job_data)

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

        # For interactive, we set the command to sleep infinity
        if context.get("interactive") is True:
            context.interactive = False
            import IPython

            IPython.embed()

        # 2. We then need to wait until the job is running or fails
        print("[yellow]Waiting for Job to start... (Timeout: 5 minutes)[/yellow]")

        # Create job objects (and eventually pod)
        job = objects.KubernetesJob(job_name, namespace)
        pod = None

        # This assumes a backoff / retry of 1, so we aren't doing recreation
        # If it fails once, it fails once and for all.
        # 30 * 5s = 150s (2.5 minutes!)
        for i in range(30):

            # 1. Check the parent Job's status for a quick terminal state
            job_status = job.get_status()
            if job_status and job_status.get("succeeded", 0) > 0:
                # The job is done, try to get logs and report success
                print("[green]✅ Job has Succeeded.[/green]")
                break

            # Womp womp
            if job_status.get("failed", 0) > 0:
                logger.error("Job reports Failed.", title="Job Status")
                diagnostics = self.get_diagnostics(job, pod)
                job.delete()
                return (
                    1,
                    f"Job entered failed state. This usually happens after repeated pod failures.\n\n{diagnostics}",
                )

            # 2. If the job isn't terminal, find the pod. It may not exist yet.
            pod = pod or job.get_pod_name()

            # 3. If a pod exists, inspect it deeply for fatal errors or readiness.
            if pod:
                pod_info = pod.get_info()
                if pod_info:
                    pod_status = pod_info.get("status", {})
                    pod_phase = pod_status.get("phase")

                    # If the pod is running and its containers are ready, we can log.
                    # Note that after we add init containers, this will need tweaking
                    if pod_phase == "Running":
                        container_statuses = pod_status.get("containerStatuses", [])
                        if all(cs.get("ready") for cs in container_statuses):
                            print(f"[green]✅ Pod '{pod.name}' is Ready.[/green]")
                            break

                    # If the pod succeeded already, we can also proceed...
                    if pod_phase == "Succeeded":
                        print(f"[green]✅ Pod '{pod.name}' has Succeeded.[/green]")
                        break

                    # This is important because a pod can be active, but then go into a crashed state
                    # We provide the status that coincides with our info query to be consistent
                    if reason := pod.has_failed_container(pod_status):
                        diagnostics = self.get_diagnostics(job, pod)
                        job.delete()
                        return (
                            1,
                            f"Pod '{pod.name}' is stuck in a fatal state: {reason}\n\n{diagnostics}",
                        )

                    print(
                        f"[dim]Job is active, Pod '{pod.name}' has status '{pod_phase}'. Waiting... ({i+1}/60)[/dim]"
                    )

                # This means we saw the pod name, but didn't get pod info / it disappeared - let loop continue
                else:
                    print(
                        f"[dim]Job is active, but Pod '{pod.name}' disappeared. Waiting for new pod... ({i+1}/60)[/dim]"
                    )
                    pod = None

            # No pod yet, keep waiting.
            else:
                print(f"[dim]Job is active, but no pod found yet. Waiting... ({i+1}/60)[/dim]")

            time.sleep(5)

        # This gets hit when the loop is done, so we probably have a timeout
        else:
            diagnostics = self.get_diagnostics(job, pod)
            return (
                1,
                f"Timeout: Job did not reach a stable running or completed state within the time limit.\n\n{diagnostics}",
            )

        # Let's try to stream logs!
        print("[green]🚀 Proceeding to stream logs...[/green]")
        full_logs = job.get_logs()
        pod.wait_for_ready()

        # Save logs regardless of success or not (so we see change)
        self.save_log(full_logs)

        # The above command will wait for the job to complete, so this should be OK to do.
        is_active = True
        while is_active:
            final_status = job.get_status()
            is_active = final_status.get("active", 0) > 0
            time.sleep(5)

        # But did it succeed?
        if final_status.get("succeeded", 0) > 0:
            print("\n[green]✅ Job final status is Succeeded.[/green]")
        else:
            print("\n[red]❌ Job final status is Failed.[/red]")
            diagnostics = self.get_diagnostics(job, pod)
            job.delete()
            # We already have the logs, so we can pass them directly.
            return 1, prompts.failure_message % diagnostics

        if cleanup and os.path.exists(deploy_dir):
            print(f"[dim]Cleaning up temporary deploy directory: {deploy_dir}[/dim]")
            job.delete()
            shutil.rmtree(deploy_dir, ignore_errors=True)

        # Save full logs for the step
        return 0, full_logs

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

    @timed
    def generate_job_manifest(self, context):
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
            job_crd = self.get_code_block(content, "yaml")
            context.result = job_crd
            self.save_job_manifest(job_crd)
            return job_crd

        except Exception as e:
            sys.exit(f"Error parsing response from Gemini: {e}\n{content}")
