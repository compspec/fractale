import fractale.agent.defaults as defaults
from fractale.agent.prompts import prompt_wrapper

# Requirements are separate to give to error helper agent
requires = """
- Please deploy to the default namespace.
- Do not create or require abstractions beyond the Job (no ConfigMap or Volume or other types)
- Do not create or require external data. Use example data provided with the app or follow instructions.
- Do not add resources, custom entrypoint/args, affinity, init containers, nodeSelector, or securityContext unless explicitly told to.
- Assume that needed software is on the PATH, and don't specify full paths to executables.
- Set the backoff limit to 1, assuming if it does not work the first time, it will not.
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


def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    prompt = regenerate_prompt % (context.error_message)
    return prompt_wrapper(prompt, context=context)


generate_prompt = (
    f"""You are a Kubernetes job generator service expert. I need to create a YAML manifest for a Kubernetes Job in an environment for '%s' for the exact container named '%s'.

Please generate a robust, production-ready manifest.
"""
    + common_instructions
)


def get_generate_prompt(context):
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    no_pull = context.get("no_pull", True)
    prompt = generate_prompt % (environment, container)
    return prompt_wrapper(add_no_pull(prompt, no_pull=no_pull), context=context)


def add_no_pull(prompt, no_pull=False):
    if no_pull:
        prompt += "- Please set the imagePullPolicy of the main container to Never.\n"
    return prompt


meta_bundle = f"""
--- JOB DESCRIPTION ---
%s

--- POD(S) DESCRIPTION ---
%s

--- NAMESPACE EVENTS (Recent) ---
%s
"""

failure_message = """Job failed during execution.

--- Diagnostics ---
%s
%s"""
