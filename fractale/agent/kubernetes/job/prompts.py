import json

import fractale.agent.defaults as defaults
import fractale.agent.kubernetes.prompts as prompts
from fractale.agent.prompts import Prompt

persona = "You are a Kubernetes Job generator expert."

# Requirements are separate to give to error helper agent
# This should explicitly state what the agent is capable of doing.
requires = prompts.common_requires + [
    "Do not create or require abstractions beyond the Job (no ConfigMap or Volume or other types)",
    "Set the backoff limit to 1, assuming if it does not work the first time, it will not.",
    "Set the restartPolicy to Never so we can inspect the logs of failed jobs",
    "You are only scoped to edit the Job manifest for Kubernetes.",
]

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

generate_task = """I need to create a YAML manifest for a Kubernetes Job in an environment for '{{environment}}' for the exact container named '{{container}}'.

Please generate a robust, production-ready manifest.
"""

generate_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": generate_task,
    "instructions": prompts.common_instructions + requires,
}


def get_update_prompt(manifest, updates):
    prompt = Prompt(update_prompt)
    return prompt.render({"manifest": manifest, "updates": updates})


optimize_instructions = [
    "You must ONLY return a json structure to be loaded that includes a limited set of fields (with keys corresponding to the names that are organized the same as a Kubernetes abstraction.",
    "The result MUST be provided as json. The fields should map 1:1 into a pod spec serialzied as json.",
    "You MUST NOT make requests that lead to Guaranteed pods.",
    "DO NOT CHANGE PROBLEM SIZE PARAMETERS OR COMMAND. You can change args.",
    "Remember that to get a full node resources you often have to ask for slightly less than what is available.",
]

optimize_task = """
Your task is to optimize the running of a Kubernetes abstraction: {{optimize}} in {{environment}}. You are allowed to request anywhere in the range of available resources, including count and type. Here are the available resources:
    {{resources}}
    Here is the current manifest:
    ```yaml
    {{manifest}}
    ```{% if dockerfile %}
    Here is the Dockerfile that helped to generate the application.
    {{dockerfile}}{% endif %}
"""

optimize_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": optimize_task,
    "instructions": prompts.common_instructions + requires + optimize_instructions,
}

regenerate_prompt = {
    "persona": persona,
    "context": prompts.common_context,
    "task": prompts.regenerate_task,
    "instructions": [],
}


def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    prompt = Prompt(regenerate_prompt, context)
    return prompt.render({"task": context.error_message})


def get_optimize_prompt(context, resources):
    """
    Get a description of cluster resources and optimization goals.
    """
    return Prompt(optimize_prompt).render(
        {
            "optimize": context.optimize,
            "environment": context.environment,
            "resources": json.dumps(resources),
            "manifest": context.result,
            "dockerfile": context.get("dockerfile"),
        }
    )


def get_generate_prompt(context):
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull")
    if no_pull is True:
        generate_prompt["instructions"].append("Set the container imagePullPolicy to Never.")

    # Populate generate prompt fields
    return Prompt(generate_prompt, context).render(
        {"environment": environment, "container": container}
    )


meta_bundle = """
--- Job Description ---
%s

--- Pod Description ---
%s

--- Events (Recent) ---
%s
"""

failure_message = """Job failed during execution.
%s"""

overtime_message = """Job was executing, but went over acceptable time of %s seconds.
%s"""
