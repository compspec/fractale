import fractale.agent.defaults as defaults
import fractale.agent.kubernetes.prompts as prompts
from fractale.agent.prompts import Prompt

persona = "You are a Kubernetes Flux Framework MiniCluster expert. You know how to write CRDs for the Flux Operator in Kubernetes."

# Requirements are separate to give to error helper agent
# This should explicitly state what the agent is capable of doing.
requires = prompts.common_requires + [
    "You MUST NOT create or require abstractions beyond the MiniCluster (no ConfigMap or Volume or other types)",
    "You MUST set spec.logging.strict to true",
    "You are only scoped to edit the MiniCluster manifest for Kubernetes.",
    "DO NOT CREATE A KUBERNETES JOB. You are creating a Flux MiniCluster deployed by the Flux Operator.",
    "You MUST set cleanup to false and you MUST set launcher to false",
    "You MUST NOT put a flux run or flux submit in the command. It is added by the Flux Operator."
    "You MUST use version v1alpha2 of the flux-framework.org minicluster.",
    "You MUST NOT add any sidecars. The list of containers should only have one entry.",
    "The command is a string and not an array. Do not edit the flux view container image.",
]


generate_task = """I need to create a YAML manifest for a MiniCluster in an environment for '{{environment}}' for the exact container named '{{container}}'. {{testing}}

Here is what a MiniCluster looks like:

{{minicluster}}

Please generate a robust, production-ready manifest.
"""

# A structured data for prompts is assembled for each task
generate_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": generate_task,
    "instructions": prompts.common_instructions + requires,
}

regenerate_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": prompts.regenerate_task,
    "instructions": [],
}

# These are snippets to go with error output.


def get_explain_prompt(minicluster_explain):
    """
    Ensure we return the explained minicluster object.
    """
    return f"As a reminder, the MiniCluster Custom Resource Definition allows the following:\n{minicluster_explain}"


update_instructions = [
    "You are NOT allowed to make other changes to the manifest",
    'Ignore the "decision" field and if you think appropriate, add context from "reason" as comments.',
    "Return ONLY the YAML with no other text or commentary.",
]

update_task = """Your job is to take a spec of updates for a Kubernetes manifest and apply them.
Here are the updates:

{{updates}}

And here is the Job manifest to apply them to:
{{manifest}}
"""

update_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": update_task,
    "instructions": prompts.common_instructions + requires + update_instructions,
}


def get_update_prompt(manifest, updates):
    prompt = Prompt(update_prompt, {"manifest": manifest, "updates": updates})
    return prompt.render({"manifest": manifest, "updates": updates})


def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    prompt = Prompt(regenerate_prompt, context)
    testing = context.get("testing")
    return prompt.render({"task": context.error_message, "testing": testing})


def get_generate_prompt(context, minicluster_explain):
    """
    Populate a prompt to generate an initial build.
    """
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull")
    testing = context.get("testing")
    if no_pull is True:
        generate_prompt["instructions"].append("Set the container imagePullPolicy to Never.")

    # Populate generate prompt fields
    return Prompt(generate_prompt, context).render(
        {
            "environment": environment,
            "container": container,
            "minicluster": minicluster_explain,
            "testing": testing,
        }
    )
