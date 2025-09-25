import json

import fractale.agent.defaults as defaults
import fractale.agent.kubernetes.prompts as prompts
from fractale.agent.prompts import Prompt

optimize_persona = "You are a Kubernetes optimization agent."
persona = "You are a Kubernetes Job generator expert."

optimize_requires = prompts.common_requires + [
    "Do not create or require additional abstractions (no ConfigMap or Volume or other types)",
    "You are only scoped to edit the provided manifest for Kubernetes.",
]

# Requirements are separate to give to error helper agent
# This should explicitly state what the agent is capable of doing.
requires = prompts.common_requires + [
    "Do not create or require additional abstractions beyond the Job (no ConfigMap or Volume or other types)",
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

generate_task = """I need to create a YAML manifest for a Kubernetes Job in an environment for '{{environment}}' for the exact container named '{{container}}'. {{ testing }}

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
{% if was_unsuccessful %}Your last attempt was not successful, so you should return to the previous configuration and not repeat the error.{% endif %}
{% if was_timeout %}Your last attempt timed out, which means you MUST reduce problem size OR increase resources (if possible){% endif %}
{% if was_unsatisfiable %}Your last attempt was unsatisfiable. The topology or other parameters might be wrong.{% endif %}
"""

optimize_function_task = """Your task is to use a function to optimize the running of a Kubernetes abstraction: {{optimize}} in {{environment}}. You MUST use this function that returns RETRY or STOP.
The provided function(s) below take in input parameters that coincide with application parameters and resources.
You MUST derive input parameters and run the function to get a response. Once you have the response, you MUST follow instructions below for what to return to me.

{{function}}

You MUST call the function to derive parameters and a 'decision' and 'reason' and updated 'manifest'. To start you can choose the parameters to best optimize. Here are the existing resources:
    {{cluster}}
    {% if resources %}Here is resource information provided by the user:
    {{resources}}{% endif %}
    Here is the current manifest:
    ```yaml
    {{manifest}}
    ```{% if dockerfile %}
    Here is the Dockerfile that helped to generate the application.
    {{dockerfile}}{% endif %}
{% if was_unsuccessful %}Your last attempt was not successful, so you should return to the previous configuration and not repeat the error.{% endif %}
{% if was_timeout %}Your last attempt timed out, which means you MUST reduce problem size OR increase resources (if possible){% endif %}
{% if was_unsatisfiable %}Your last attempt was unsatisfiable. The topology or other parameters might be wrong.{% endif %}
"""

optimize_function_instructions = [
    "You MUST format the response in a JSON string that can be parsed",
    "Your result MUST only contain fields `decision` `reason` and `manifest`"
    "The manifest MUST ONLY contain changed parameters and resources provided by the function.",
    "You MUST not make changes from what the function provides, but provide description if you add to it",
    "The decision MUST be either RETRY to redo the run (not optimized) or STOP to not proceed (optimized)",
] + optimize_instructions


optimize_prompt = {
    "persona": optimize_persona,
    "context": prompts.common_context,
    "task": optimize_task,
    "instructions": prompts.common_instructions + optimize_requires + optimize_instructions,
}

optimize_function_prompt = {
    "persona": optimize_persona,
    "context": prompts.common_context,
    "task": optimize_function_task,
    "instructions": prompts.common_instructions
    + optimize_requires
    + optimize_function_instructions,
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
    testing = context.get("testing")
    return prompt.render({"task": context.error_message, "testing": testing})


def get_optimize_prompt(context, resources):
    """
    Get a description of cluster resources and optimization goals.
    """
    if context.get("function"):
        return Prompt(optimize_function_prompt, context).render(
            {
                "optimize": context.get("optimize") or context.get("scale"),
                "function": context.function,
                "environment": context.environment,
                "resources": json.dumps(resources),
                "was_timeout": context.was_timeout,
                "was_unsatisfiable": context.was_unsatisfiable,
                "was_unsuccessful": context.get("was_unsuccessful"),
                "manifest": context.result,
                "dockerfile": context.get("dockerfile"),
            }
        )

    return Prompt(optimize_prompt, context).render(
        {
            "optimize": context.get("optimize") or context.get("scale"),
            # This is a resource spec provided by user (e.g., autoscaling cluster)
            "resources": context.get("resources"),
            "was_timeout": context.was_timeout,
            "was_unsuccessful": context.get("was_unsuccessful"),
            "was_unsatisfiable": context.was_unsatisfiable,
            "environment": context.environment,
            # These are cluster resources found
            "cluster": json.dumps(resources),
            "manifest": context.result,
            "dockerfile": context.get("dockerfile"),
        }
    )


def get_generate_prompt(context):
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull")
    testing = context.get("testing")
    if no_pull is True:
        generate_prompt["instructions"].append("Set the container imagePullPolicy to Never.")

    # Populate generate prompt fields
    return Prompt(generate_prompt, context).render(
        {"environment": environment, "container": container, "testing": testing}
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

lost_message = """Your last deploy was lost, which is not a failure. Possibly consider other strategies for another attempt.
%s
"""

lost_optimization_message = """Your last optimization attempt result was lost, which is not a failure. You MUST discard this attempt and you MUST retry. You MAY consider other strategies for another attempt.
%s
"""
