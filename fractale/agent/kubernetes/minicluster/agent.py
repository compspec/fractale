import json
import subprocess
import tempfile

import yaml
from rich import print

import fractale.agent.kubernetes.minicluster.prompts as prompts
import fractale.agent.kubernetes.objects as objects
import fractale.agent.logger as logger
from fractale.agent.context import get_context
from fractale.agent.decorators import timed
from fractale.agent.kubernetes.job import KubernetesJobAgent

flux_views = [
    "ghcr.io/converged-computing/flux-view-rocky:arm-9",
    "ghcr.io/converged-computing/flux-view-rocky:arn-8",
    "ghcr.io/converged-computing/flux-view-rocky:tag-9",
    "ghcr.io/converged-computing/flux-view-rocky:tag-8",
    "ghcr.io/converged-computing/flux-view-ubuntu:tag-noble",
    "ghcr.io/converged-computing/flux-view-ubuntu:tag-jammy",
    "ghcr.io/converged-computing/flux-view-ubuntu:tag-focal",
    "ghcr.io/converged-computing/flux-view-ubuntu:arm-jammy",
    "ghcr.io/converged-computing/flux-view-ubuntu:arm-focal",
]


class MiniClusterAgent(KubernetesJobAgent):
    """
    Create a FluxFramework Minicluster
    """

    name = "minicluster"
    description = "Kubernetes Flux MiniCluster agent"
    result_type = "flux-minicluster-manifest"

    def check_flux_view(self, minicluster):
        """
        If a view is defined, ensure it is in allowed set.
        """
        if not minicluster:
            return minicluster
        view = minicluster.get("spec", {}).get("flux", {}).get("container", {}).get("image")
        if not view:
            return minicluster
        if view not in flux_views:
            logger.warning(f"Flux view {view} is not valid and will not be used.")
            del minicluster["spec"]["flux"]["container"]
            if not minicluster["spec"]["flux"]:
                del minicluster["spec"]["flux"]
        return minicluster

    @timed
    def deploy(self, context):
        """
        Deploy the Kubernetes Job.
        """
        # Not sure if this can happen, assume it can
        if not context.result:
            raise ValueError("No MiniCluster Specification content provided.")

        # Job needs to load as yaml to work, period.
        try:
            minicluster = yaml.safe_load(context.result)
        except Exception as e:
            return (1, str(e) + "\n" + context.result)

        # Cut out early if we don't have a known name / namespace
        name = minicluster.get("metadata", {}).get("name")
        namespace = minicluster.get("metadata", {}).get("namespace", "default")
        if not name:
            return 1, "Generated YAML is missing required '.metadata.name' field."

        # This is a common error the LLM makes
        minicluster = self.check_flux_view(minicluster)

        # If it doesn't follow instructions...
        containers = self.get_containers(minicluster)
        if not containers:
            return (
                minicluster,
                1,
                "Generated YAML is missing required 'spec.containers' list field.",
            )

        # Assume one container for now, and manually we can easily check
        found_image = containers[0].get("image")
        if found_image != context.container:
            containers[0]["image"] = context.container
            minicluster["spec"]["containers"] = containers

        deploy_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary deploy context: {deploy_dir}[/dim]")

        context.result = yaml.dump(minicluster)
        mc = objects.MiniCluster(name, namespace)
        logger.info(
            f"Attempt {self.attempts} to deploy Kubernetes {mc.kind}: [bold cyan]{mc.namespace}/{mc.name}"
        )
        p = mc.apply(context.result)

        if p.returncode != 0:
            print("[red]'kubectl apply' failed. The manifest is likely invalid.[/red]")
            return (p.returncode, p.stdout + p.stderr + prompts.get_explain_prompt(self.explain()))

        print("[green]✅ Manifest applied successfully.[/green]")

        # 2. We then need to wait until the job is running or fails
        print("[yellow]Waiting for MiniCluster Job to start... (Timeout: 5 minutes)[/yellow]")

        # We finish by watching the indexed job
        job = objects.KubernetesJob(name, namespace)
        rc, message = self.finish_deploy(context, job, deploy_dir)

        # Delete the Minicluster - the job agent doesn't have the handle
        mc.delete()
        return rc, message

    def get_containers(self, job_data):
        return job_data.get("spec", {}).get("containers") or []

    def set_containers(self, job_data, containers):
        job_data["spec"]["containers"] = containers
        return job_data

    def get_prompt(self, context):
        """
        Get the prompt for the LLM. We expose this so the manager can take it
        and tweak it.
        """
        context = get_context(context)
        if context.get("error_message"):
            prompt = prompts.get_regenerate_prompt(context)
        else:
            # If we first generate, add the explain
            prompt = prompts.get_generate_prompt(context, self.explain())
        return prompt

    def update_manifest(self, updates, manifest):
        """
        Update the crd with a set of controlled fields.
        """
        for key in ["decision", "reason"]:
            if key in updates:
                del updates[key]
        prompt = prompts.get_update_prompt(manifest, json.dumps(updates))
        result = self.ask_gemini(prompt)
        return self.get_code_block(result, "yaml")

    def explain(self):
        """
        Explain the type
        """
        cmd = ["kubectl", "explain", "miniclusters", "--recursive=TRUE"]
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if p.returncode != 0:
            print("[red]'kubectl explain' failed.[/red]")
            return ""
        return p.stdout + p.stderr
