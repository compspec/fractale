import json

import fractale.agent.defaults as defaults
from fractale.agent.prompts import prompt_wrapper

# Requirements are separate to give to error helper agent
# This should explicitly state what the agent is capable of doing.
requires = """
- Please deploy to the default namespace.
- Do not create or require abstractions beyond the Job (no ConfigMap or Volume or other types)
- Do not create or require external data. Use example data provided with the app or follow instructions.
- Do not add resources, custom entrypoint/args, affinity, init containers, nodeSelector, or securityContext unless explicitly told to.
- Do NOT add resource requests or limits. The pod should be able to use the full available resources and be Burstable.
- Assume that needed software is on the PATH, and don't specify full paths to executables.
- Set the backoff limit to 1, assuming if it does not work the first time, it will not.
- Set the restartPolicy to Never so we can inspect the logs of failed jobs
- Keep in mind that an instance vCPU == 1 logical CPU. Apps typically care about logical CPU.
- You are only scoped to edit the Job manifest for Kubernetes.
"""

common_instructions = (
    """- Be mindful of the cloud and needs for resource requests and limits for network or devices.
- The response should only contain the complete, corrected YAML manifest inside a single markdown code block.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- Use succinct comments to explain build logic and changes.
- This will be a final YAML manifest - do not tell me to customize something.
"""
    + requires
)

regenerate_prompt = """Your previous attempt to generate the manifest failed. Please analyze the instruction to fix it and make another try.

%s
"""

update_prompt = """You are a Kubernetes Job update agent. Your job is to take a spec of updates for a Job Manifest and apply them.
You are NOT allowed to make other changes to the manifest. Ignore the 'decision' field and if you think appropriate, add context from "reason" as comments.
Here are the updates:

%s

And here is the Job manifest to apply them to:
%s
Return ONLY the YAML with no other text or commentary.
"""


def get_optimize_prompt(context, resources):
    """
    Get a description of cluster resources and optimization goals.
    """
    prompt = """
    Your task is to optimize the running of a Kubernetes Job: %s in %s. You are allowed to request anywhere in the range of available resources, including count and type. Here are the available resources:
    %s
    Here is the current job manifest:
    ```yaml
    %s
    ```
    Please return ONLY a json structure to be loaded that includes a limited set of fields (with keys corresponding to the names that are organized the same as a Kubernetes Job, e.g., spec -> template -spec.
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


def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    prompt = regenerate_prompt % (context.error_message)
    return prompt_wrapper(prompt, context=context)


generate_prompt = (
    """You are a Kubernetes job generator service expert. I need to create a YAML manifest for a Kubernetes Job in an environment for '%s' for the exact container named '%s'.

Please generate a robust, production-ready manifest.
"""
    + common_instructions
)


def get_generate_prompt(context):
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull")
    prompt = generate_prompt % (environment, container)
    return prompt_wrapper(add_no_pull(prompt, no_pull=no_pull), context=context)


def add_no_pull(prompt, no_pull=False):
    if no_pull is True:
        prompt += "- Please set the imagePullPolicy of the main container to Never.\n"
    return prompt


meta_bundle = """
--- JOB DESCRIPTION ---
%s

--- POD(S) DESCRIPTION ---
%s

--- NAMESPACE EVENTS (Recent) ---
%s
"""

failure_message = """Job failed during execution.
%s"""

overtime_message = """Job was executing, but went over acceptable time of %s seconds.
%s"""
