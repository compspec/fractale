import json
import os
import shutil
import sys
import tempfile
import textwrap
import time

import yaml
from rich import print

import fractale.agent.kubernetes.job.prompts as prompts
import fractale.agent.kubernetes.objects as objects
import fractale.agent.logger as logger
import fractale.utils as utils
from fractale.agent.context import get_context
from fractale.agent.decorators import timed
from fractale.agent.errors import DebugAgent
from fractale.agent.kubernetes.base import KubernetesAgent
from fractale.agent.optimize import OptimizationAgent


class KubernetesJobAgent(KubernetesAgent):
    """
    A Kubernetes Job agent knows how to design a Kubernetes job.
    """

    name = "kubernetes-job"
    description = "Kubernetes Job agent"
    result_type = "kubernetes-job-manifest"

    def __init__(self, *args, **kwargs):
        """
        Add the optimization agent, even if we don't need it.
        """
        super().__init__(*args, **kwargs)
        self.optimize_agent = OptimizationAgent()

    def get_prompt(self, context):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)
        if context.get("error_message"):
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
        manifest = self.generate_manifest(context)
        logger.custom(manifest, title=f"[green]{self.name}.yaml[/green]", border_style="green")

        # Make and deploy it! Success is exit code 0.
        return_code, output = self.deploy(context)
        if return_code == 0:
            self.print_result(manifest)
            logger.success(f"Deploy complete in {self.attempts} attempts")
        else:
            logger.error(f"Deploy failed:\n{output[-1000:]}", title="Deploy Status")
            print(
                f"\n[bold cyan] Requesting Correction from Kubernetes {self.name.capitalize()} Agent[/bold cyan]"
            )

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
            context.result = manifest
            return self.run_step(context)

        self.write_file(context, manifest)
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

    def get_diagnostics(self, obj, pod):
        """
        Helper to collect error data for a failed job.
        """
        print(f"[yellow]Gathering diagnostics for failed {obj.kind}...[/yellow]")
        pod_events = []
        pods_description = ""
        if pod is not None:
            pod_status = pod.get_filtered_status()
            pod_events = pod.get_events()
            pods_description = json.dumps(pod_status)

        job_status = obj.get_filtered_status()

        # Use json.dumps because it's more compact (maybe fewer tokens)
        job_events = obj.get_events()
        events = sorted(job_events + pod_events, key=lambda e: e.get("lastTimestamp", ""))
        job_description = json.dumps(job_status)
        events_description = json.dumps(events)

        # This is assumed to be a one shot
        full_logs = obj.get_logs(wait=False)

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
        # Not sure if this can happen, assume it can
        if not context.result:
            raise ValueError("No Job Specification content provided.")

        # Job needs to load as yaml to work, period.
        try:
            job_data = yaml.safe_load(context.result)
        except Exception as e:
            return (1, str(e) + "\n" + context.result)

        # Cut out early if we don't have a known name / namespace
        job_name = job_data.get("metadata", {}).get("name")
        namespace = job_data.get("metadata", {}).get("namespace", "default")
        if not job_name:
            return 1, "Generated YAML is missing required '.metadata.name' field."

        # If it doesn't follow instructions...
        job_data, return_code, message = self.check(context, job_data)
        if return_code != 0:
            return return_code, message
        context.result = yaml.dump(job_data)
        deploy_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary deploy context: {deploy_dir}[/dim]")

        # The debugger can decide to give the user an interactive session
        # For interactive, we set the command to sleep infinity
        if context.get("interactive") is True:
            logger.info(
                f"Starting Interative Debugging Session: job manifest in => {deploy_dir}\nType 'exit' when done."
            )
            containers = self.get_containers(job_data)
            command = containers[0]["command"]
            logger.custom(f"  Initial command: {command}")
            containers[0]["command"] = ["sleep", "infinity"]
            job_data = self.set_containers(job_data, containers)
            context.result = yaml.dump(job_data)


        # Create job objects (and eventually pod)
        # But ensure we delete any that might exist from before.
        job = objects.KubernetesJob(job_name, namespace)
        logger.info(
            f"Attempt {self.attempts} to deploy Kubernetes {job.kind}: [bold cyan]{job.namespace}/{job.name}"
        )
        p = job.apply(context.result)

        if p.returncode != 0:
            print("[red]'kubectl apply' failed. The manifest is likely invalid.[/red]")
            return (p.returncode, p.stdout + p.stderr)

        print("[green]✅ Manifest applied successfully.[/green]")

        # For interactive, we set the command to sleep infinity
        if context.get("interactive") is True:
            context.interactive = False
            import IPython

            IPython.embed()

        # 2. We then need to wait until the job is running or fails
        print("[yellow]Waiting for Job to start... (Timeout: 5 minutes)[/yellow]")
        return self.finish_deploy(context, job, deploy_dir)

    def finish_deploy(self, context, obj, deploy_dir):
        """
        Watch for pod / job object and finish deployment.
        """
        pod = None

        # This assumes a backoff / retry of 1, so we aren't doing recreation
        # If it fails once, it fails once and for all.
        # 30 * 5s = 150s (2.5 minutes!)
        for i in range(30):

            # 1. Check the parent Job's status for a quick terminal state
            status = obj.get_status()
            if status and status.get("succeeded", 0) > 0:
                # The job is done, try to get logs and report success
                print("[green]✅ MiniCluster Job has Succeeded.[/green]")
                break

            # Womp womp
            if status.get("failed", 0) > 0:
                logger.error("Job reports Failed.", title="Job Status")
                diagnostics = self.get_diagnostics(obj, pod)
                obj.delete()
                return (
                    1,
                    f"Job entered failed state. This usually happens after repeated pod failures.\n\n{diagnostics}",
                )

            # 2. If the job isn't terminal, find the pod. It may not exist yet.
            tries = 0
            while not pod and tries < 10:
                print("Waiting for pod...")
                pod = obj.get_pod()
                time.sleep(5)
                tries += 1

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
                        diagnostics = self.get_diagnostics(obj, pod)
                        obj.delete()
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
            diagnostics = self.get_diagnostics(obj, pod)
            return (
                1,
                f"Timeout: Job did not reach a stable running or completed state within the time limit.\n\n{diagnostics}",
            )

        # Let's try to stream logs!
        print("[green]🚀 Proceeding to stream logs...[/green]")
        full_logs = obj.get_logs(context.get("max_runtime"))
        pod.wait_for_ready()

        # Save logs regardless of success or not (so we see change)
        self.save_log(full_logs)

        # The above command will wait for the job to complete, so this should be OK to do.
        is_active = True
        wait_seconds = 0
        max_runtime_seconds = context.get("max_runtime")
        while is_active:
            final_status = obj.get_status()
            is_active = final_status.get("active", 0) > 0

            # This is the case where we (the user) set an upper limit
            if max_runtime_seconds is not None and max_runtime_seconds > wait_seconds:
                print("\n[red]❌ Job has exceeded acceptable time.[/red]")
                diagnostics = self.get_diagnostics(obj, pod)
                import IPython 
                IPython.embed()
                obj.delete()
                return 1, prompts.overtime_message % (max_runtime_seconds, diagnostics)

            wait_seconds += 5
            time.sleep(5)

        # But did it succeed?
        if final_status.get("succeeded", 0) > 0:
            print("\n[green]✅ Job final status is Succeeded.[/green]")

            # if we want to optimize, we continue to run until we are instructed not to.
            if context.get("optimize") is not None:
                return self.optimize(context, obj, context.result, full_logs)

        else:
            print("\n[red]❌ Job final status is Failed.[/red]")
            diagnostics = self.get_diagnostics(obj, pod)
            obj.delete()
            # We already have the logs, so we can pass them directly.
            return 1, prompts.failure_message % diagnostics

        if context.get("cleanup") is True and os.path.exists(deploy_dir):
            print(f"[dim]Cleaning up temporary deploy directory: {deploy_dir}[/dim]")
            obj.delete()
            shutil.rmtree(deploy_dir, ignore_errors=True)

        # Save full logs for the step
        return 0, full_logs

    def optimize(self, context, job, job_crd, full_logs):
        """
        Optimize the run.
        """
        # We should provide the cluster resources to the agent
        resources = self.cluster_resources()

        # The agent calling the optimize agent decides what metadata to present.
        # This is how this agent will work for cloud vs. bare metal
        context.requires = prompts.get_optimize_prompt(context, resources)
        context = self.optimize_agent.run(context, full_logs)

        # Go through spec and update fields that match.
        decision = context.optimize_result["decision"]
        print(f"\n[green]✅ Optimization agent decided to {decision}.[/green]")
        if decision == "RETRY":

            # Retry will mean recreating job
            job.delete()
            context.result = self.update_manifest(context.optimize_result, job_crd)
            print(context.result)
            return self.deploy(context)

        # Agent has decided to return - no more optimize.
        # TODO: we need to ensure regex can be passed from context (and input)
        # Here we add the optimization agent metadata the agent here for saving
        self.optimize_agent.metadata["foms"] = self.optimize_agent.foms
        self.metadata["assets"]["optimize"] = self.optimize_agent.metadata
        return 0, full_logs

    def get_containers(self, job_data):
        return job_data.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or []

    def set_containers(self, job_data, containers):
        job_data["spec"]["template"]["spec"]["containers"] = containers
        return job_data

    def check(self, context, job_data):
        """
        Check the data. Allow fixing common issues the LLM runs into.
        """
        containers = self.get_containers(job_data)
        if not containers:
            return job_data, 1, "Generated YAML is missing required '.containers' list field."

        # Assume one container for now, and manually we can easily check
        found_image = containers[0].get("image")
        if found_image != context.container:
            containers[0]["image"] = context.container
            job_data["spec"]['template"']["spec"]["containers"] = containers
        return job_data, 0, ""

    def update_manifest(self, updates, job_crd):
        """
        Update the job crd with a set of controlled fields.
        """
        for key in ["decision", "reason"]:
            if key in updates:
                del updates[key]
        prompt = prompts.update_prompt % (job_crd, json.dumps(updates))
        result = self.ask_gemini(prompt)
        return self.get_code_block(result, "yaml")

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
    def generate_manifest(self, context):
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
