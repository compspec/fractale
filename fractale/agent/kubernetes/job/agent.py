import copy
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
from fractale.agent.scaling import ScalingAgent


class KubernetesJobAgent(KubernetesAgent):
    """
    A Kubernetes Job agent knows how to design a Kubernetes job.
    """

    name = "kubernetes-job"
    description = "Kubernetes Job agent"
    result_type = "kubernetes-job-manifest"

    def __init__(self, *args, **kwargs):
        """
        Add the optimization and scaling agents, even if we don't need it.
        """
        super().__init__(*args, **kwargs)
        self.optimize_agent = OptimizationAgent()
        self.scaling_agent = ScalingAgent()

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

    def validate(self, context):
        """
        Validation for the context.
        """
        # If we are requesting a scale, we need the sizes.
        if context.get("scale") is not None:
            sizes = context.get("sizes")
            if sizes is None:
                raise ValueError("The 'sizes' field is required in context to scale.")
            if not isinstance(sizes, list):
                raise ValueError("The 'sizes' field must be a list")
            if any([not isinstance(x, int) for x in sizes]):
                raise ValueError("Each entry in 'sizes' must be an integer")

    @timed
    def run_step(self, context):
        """
        Run the agent.
        """
        # These are required, context file is not (but recommended)
        context = self.add_build_context(context)
        self.validate(context)

        # This will either generate fresh or rebuild erroneous Job
        manifest = self.generate_manifest(context)
        logger.custom(manifest, title=f"[green]{self.name}.yaml[/green]", border_style="green")

        # Make and deploy it! Success is exit code 0.
        return_code, output = self.deploy(context)
        if return_code == 0:
            self.print_result(manifest)
            logger.success(f"Deploy complete in {self.attempts} attempts")
        else:
            return self.handle_failed_job(context, output, manifest)
        self.write_file(context, manifest)
        return context

    def handle_failed_job(self, context, output, manifest):
        """
        Handle a failed job
        """
        logger.error(f"Deploy failed or lost:\n{output[-1000:]}", title="Deploy Status")
        print(
            f"\n[bold cyan] Requesting Correction from Kubernetes {self.name.capitalize()} Agent[/bold cyan]"
        )

        # Ask the debug agent to better instruct the error message
        context.error_message = output

        # This updates the error message to be the output
        context = DebugAgent().run(context, requires=prompts.requires)

        # Update and reset return to human. We don't touch return to manager (done below)
        self.reset_return_actions(context)

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
        full_logs, _ = obj.get_logs(wait=False)

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

        # 2. We then need to wait until the job is running or fails
        print("[yellow]Waiting for Job to start... (Timeout: 5 minutes)[/yellow]")
        return self.finish_deploy(context, job, deploy_dir)

    def finish_deploy(self, context, obj, deploy_dir, callback=None):
        """
        Watch for pod / job object and finish deployment.
        """
        pod = None

        def cleanup(callback, obj):
            obj.delete()
            if callback is not None:
                callback()

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
                cleanup(callback, obj)
                return (
                    1,
                    f"Job entered failed state. This usually happens after repeated pod failures.\n\n{diagnostics}",
                )

            # 2. If the job isn't terminal, find the pod. It may not exist yet.
            tries = 0
            while not pod and tries < 10:
                print("Waiting for pod...", end="\r")
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

                        # If the pod was OOMKIlled, this shouldn't cycle around as failure during optimization
                        if reason == "OOMKilled" and context.get("is_optimizing"):
                            print(f"[orange]Pod '{pod.name}' was OOMKilled.[/orange]")
                            cleanup(callback, obj)
                            return self.optimize(
                                context, obj, context.result, "The last attempt was OOMKilled."
                            )

                        diagnostics = self.get_diagnostics(obj, pod)
                        cleanup(callback, obj)
                        return (
                            1,
                            f"Pod '{pod.name}' is stuck in a fatal state: {reason}\n\n{diagnostics}",
                        )

                    print(
                        f"[dim]Job is active, Pod '{pod.name}' has status '{pod_phase}'. Waiting... ({i+1}/60)[/dim]",
                        end="\r",
                    )

                # This means we saw the pod name, but didn't get pod info / it disappeared - let loop continue
                else:
                    print(
                        f"[dim]Job is active, but Pod '{pod.name}' disappeared. Waiting for new pod... ({i+1}/60)[/dim]",
                        end="\r",
                    )
                    pod = None

            # No pod yet, keep waiting.
            else:
                print(
                    f"[dim]Job is active, but no pod found yet. Waiting... ({i+1}/60)[/dim]",
                    end="\r",
                )

            time.sleep(5)

        # This gets hit when the loop is done, so we probably have a timeout
        else:
            cleanup(callback, obj)
            diagnostics = self.get_diagnostics(obj, pod)
            return (
                1,
                f"Timeout: Job did not reach a stable running or completed state within the time limit.\n\n{diagnostics}",
            )

        # Let's try to stream logs!
        print("[green]🚀 Proceeding to stream logs...[/green]")

        # This function takes the max runtime and will stream until it passes, or the pod exits
        pod.wait_for_ready()
        full_logs, was_timeout = obj.get_logs(context.get("max_runtime"))
        context.was_timeout = was_timeout
        final_status = pod.wait_for_complete()

        # Sometimes Kubernetes is racey, allow to complete fully
        time.sleep(3)

        # Save logs regardless of success or not (so we see change)
        self.save_log(full_logs)
        context.was_unsatisfiable = "unsatisfiable" in full_logs

        # But did it succeed?
        to_optimizing = context.get("is_optimizing") is True
        to_scaling = context.get("scale") is not None and not to_optimizing
        print(f"To optimizing: {to_optimizing}")
        print(f"To scaling: {to_scaling}")

        # Always get diagnostics in case we need, to cleanly clean up
        diagnostics = self.get_diagnostics(obj, pod)
        cleanup(callback, obj)

        # Success case. Are we still scaling?
        if final_status == "Succeeded":
            print("\n[green]✅ Job final status is Succeeded.[/green]")

            # We were scaling and optimizing OR just optimizing, keep going
            if to_optimizing:
                return self.optimize(context, obj, context.result, full_logs)
            elif to_scaling:
                return self.scale(context, obj, full_logs)

        # Failed container issue - try debugging.
        elif final_status in objects.container_issues:
            message = f"Container failed with status: {final_status}"
            # if to_optimizing:
            #    return self.optimize(context, obj, context.result, message)
            return 1, message

        elif final_status == "Lost":
            print("\n[orange]Job was erroneously lost, will retry[/orange]")

            # If we are optimizing, tell the agent that the last attempt failed.
            if to_optimizing:
                full_logs = prompts.lost_optimization_message % full_logs
                return self.optimize(context, obj, context.result, full_logs)
            return 1, prompts.lost_message % full_logs

        # If we were optimizing and it was too long, return to optimization agent
        # Or we were optimizing and the resource was unsatisfiable
        elif (to_optimizing and context.was_timeout) or (
            to_optimizing and context.was_unsatisfiable
        ):
            return self.optimize(context, obj, context.result, full_logs)

        else:
            print("\n[red]❌ Job final status is Failed.[/red]")

            # We already have the logs, so we can pass them directly.
            return 1, prompts.failure_message % diagnostics

        if context.get("cleanup") is True and os.path.exists(deploy_dir):
            print(f"[dim]Cleaning up temporary deploy directory: {deploy_dir}[/dim]")
            shutil.rmtree(deploy_dir, ignore_errors=True)

        # Save full logs for the step
        return 0, full_logs

    def optimize(self, context, job, job_crd, full_logs):
        """
        Optimize the run.
        """
        # indicator that we started optimizing. We do this so we don't go back to trying to run again
        context.is_optimizing = True

        # Don't allow returning to manager once we've started.
        context.return_to_manager = False

        # We should provide the cluster resources to the agent
        resources = self.cluster_resources()

        # The agent calling the optimize agent decides what metadata to present.
        # This is how this agent will work for cloud vs. bare metal
        # This first prompt provides resources.
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
        context.is_optimizing = False
        return 0, full_logs

    def scale(self, context, job, full_logs):
        """
        Scale the run, optimizing at each size.

        This is executed after an initial successful deployment.
        """
        # If we haven't cached the sizes
        extra = ""
        if "sizes" not in self.metadata["assets"]:
            self.metadata["assets"]["sizes"] = copy.deepcopy(context.sizes)
            extra = "This is the first size of a scaling study."
            context.scaling_attempts = {}

        # If we have no more sizes, we are done
        if not context.sizes:
            return 0, full_logs

        # Iterate through sizes, and honor order provided
        context.size = context.sizes.pop(0)
        decision = "RETRY"
        specs = {}
        holder = copy.deepcopy(context.optimize)
        while decision != "STOP":

            # We need to provide the optimization agent with a prompt that includes the size
            context.optimize = f"You MUST optimize for {context.size} nodes.\n{extra}\n{holder}"

            # After we set this once, we never want to set it again.
            extra = ""

            # This is the final, optimized result for a specific size
            # This outer loop ensures we exit when optimize is successful
            return_code = -1
            while return_code != 0:
                return_code, final_log = self.optimize(context, job, context.result, full_logs)

                # If the optimization run resulted in a deployment failure, stop and
                # return the error code so run_step() can trigger the DebugAgent.
                if return_code != 0:
                    context.is_optimizing = False

                    # Add the size back!
                    context.sizes.insert(0, context.size)
                    context.optimize = holder
                    return return_code, final_log

            # Save the result when we exit.
            best_fom = context.optimize_result.get("best_fom")
            print(best_fom)

            context.scaling_attempts[context.size] = best_fom

            # Restore the initial optimize prompt
            context.optimize = holder

            # We now give this result to the scaling agent, and ask how it wants to proceed.
            context = self.scaling_agent.run(context)
            specs[context.size] = context.scaling_result
            decision = context.scaling_result["decision"]
            print(f"\n[green]✅ Scaling agent decided on {decision}.[/green]")

            # Uodate to next size
            if decision == "PROCEED" and context.sizes:
                context.size = context.sizes.pop(0)
            elif decision == "PROCEED" and not context.sizes:
                decision = "STOP"

            # Alert the user
            if decision == "STOP":
                print(f"\n[dim][x] Stopping scaling.[/dim]")

                # Restore sizes (that have all been popped)
                context.sizes = self.metadata["assets"]["sizes"]
                del self.metadata["assets"]["sizes"]

                # Agent has decided to return - no more optimize.
                self.metadata["assets"]["scaling"] = specs
        return 0, final_log

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

    def update_manifest(self, updates, manifest):
        """
        Update the crd with a set of controlled fields.
        """
        for key in ["decision", "reason"]:
            if key in updates:
                del updates[key]
        # This is faster than asking the agent to do it
        if "manifest" in updates:
            updates = self.get_code_block(updates["manifest"], "yaml")

        prompt = prompts.get_update_prompt(manifest, json.dumps(updates))
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
