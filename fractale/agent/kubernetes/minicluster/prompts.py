import json

import fractale.agent.defaults as defaults
import fractale.agent.kubernetes.prompts as prompts
from fractale.agent.prompts import prompt_wrapper

# Requirements are separate to give to error helper agent
# This should explicitly state what the agent is capable of doing.
requires = (
    prompts.common_requires
    + """
- Do not create or require abstractions beyond the MiniCluster (no ConfigMap or Volume or other types)
- You are only scoped to edit the MiniCluster manifest for Kubernetes.
- DO NOT CREATE A KUBERNETES JOB. You are creating a Flux MiniCluster deployed by the Flux Operator.
- You must use version v1alpha2 of the flux-framework.org minicluster.
- Do not add any sidecars. The list of containers should only have one entry.
- The command is a string and not an array. You MUST set launcher to false. Do not edit the flux view container image.
"""
)

common_instructions = prompts.common_instructions + requires

update_prompt = """You are a Kubernetes Flux Framework MiniCluster agent. Your task is to take a spec of updates for a Flux Framework MiniCluster Manifest (v1alpha2) and apply them.
You are NOT allowed to make other changes to the manifest. Ignore the 'decision' field and if you think appropriate, add context from "reason" as comments.
Here are the updates:

%s

And here is the manifest to apply them to:
%s
Return ONLY the YAML with no other text or commentary.
"""


def get_optimize_prompt(context, resources):
    """
    Get a description of cluster resources and optimization goals.
    """
    prompt = """
    Your task is to optimize the running of a Kubernetes Flux Framework MiniCluster: %s in %s. You are allowed to request anywhere in the range of available resources, including count and type. Here are the available resources:
    %s
    Here is the current manifest:
    ```yaml
    %s
    ```
    Please return ONLY a json structure to be loaded that includes a limited set of fields (with keys corresponding to the names that are organized the same as a Kubernetes MiniCluster.
    The result should be provided as json. The fields should map 1:1 into a pod spec serialzied as json.
    Do not make requests that lead to Guaranteed pods. DO NOT CHANGE PROBLEM SIZE PARAMETERS OR COMMAND. You can change args. Remember that
    to get a full node resources you often have to ask for slightly less than what is available.
    """ % (
        context.optimize,
        context.environment,
        json.dumps(resources),
        context.result,
    )
    dockerfile = context.get("dockerfile")
    if dockerfile:
        prompt += (
            f" Here is the Dockerfile that helped to generate the application.\n {dockerfile}\n"
        )
    return prompt

def get_explain_prompt(minicluster_explain):
    """
    Ensure we return the explained minicluster object.
    """
    return f"As a reminder, the MiniCluster Custom Resource Definition allows the following:\n{minicluster_explain}"

def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    prompt = prompts.regenerate_prompt % context.error_message
    return prompt_wrapper(prompt, context=context)


generate_prompt = (
    """You are a Kubernetes Flux Framework MiniCluster expert - you know how to write CRDs for the Flux Operator in Kubernetes. I need to create a YAML manifest for a MiniCluster in an environment for '%s' for the exact container named '%s'.

Here is what a MiniCluster looks like:

%s

Please generate a robust, production-ready manifest.
"""
    + common_instructions
)


def get_generate_prompt(context, minicluster_explain):
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull")
    prompt = generate_prompt % (environment, container, minicluster_explain)
    return prompt_wrapper(add_no_pull(prompt, no_pull=no_pull), context=context)


def add_no_pull(prompt, no_pull=False):
    if no_pull is True:
        prompt += "- Set the container imagePullPolicy to Never.\n"
    return prompt
