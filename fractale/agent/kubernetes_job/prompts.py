import fractale.agent.defaults as defaults
from fractale.agent.prompts import prompt_wrapper

# Requirements are provided to the manager to know how to prepare the context
requires = """I am a Kubernetes Job generator and deployment agent. I accept the following inputs to be in my context:

build_context: (optional but suggested) should be a previously used dockerfile that can provide
hints to the execution. If a previous execution was attempted and there is error, it should be
provided here.

container: (required) The exact name of the image that should appear as the image for the Job.

no_pull: A boolean (True or False) that indicates if the container should not be pulled (False indicates Never)

environment: (optional) The name of the expected environment to deploy the Kubernetes job to. If an environment
was previously provided, it should be included.
"""

common_instructions = """- Be mindful of the cloud and needs for resource requests and limits for network or devices.
- The response should only contain the complete, corrected YAML manifest inside a single markdown code block.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- Use succinct comments to explain build logic and changes.
- This will be a final YAML manifest - do not tell me to customize something.
- Please deploy to the default namespace.
- Do not create or require abstractions beyond the Job (no ConfigMap or Volume or other types)
- Do not create data. Use example data provided with the app or follow instructions.
- Do not add resources, custom entrypoint/args, affinity, init containers, nodeSelector, or securityContext unless explicitly told to.

"""

regenerate_prompt = (
    f"""Act as a Kubernetes job generator service expert. I am trying to write a YAML manifest for a Kubernetes Job in an environment for '%s' and the exact named application container `%s`. The previous attempt to generate the manifest failed. Here is the problematic manifest:

```yaml
%s
```

Here is the original context to make it:

```dockerfile
%s
```

Here is the error message I received:
```
%s
```

Please analyze the error and the manifest, and provide a corrected version.
"""
    + common_instructions
)


def get_regenerate_prompt(context):
    """
    Regenerate is called only if there is an error message.
    """
    environment = context.get("environment", defaults.environment)
    container = context.get("container", required=True)
    template = context.get("job_crd", "")
    dockerfile = context.get("build_context", "")
    no_pull = context.get("no_pull")
    prompt = regenerate_prompt % (
        environment,
        container,
        template,
        dockerfile,
        context.error_message,
    )
    return prompt_wrapper(add_no_pull(prompt, no_pull), context=context)


generate_prompt = (
    f"""Act as a Kubernetes job generator service expert. I need to create a YAML manifest for a Kubernetes Job in an environment for '%s' for the exact container named '%s'.

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
        prompt += "- Please set the imagePullPolicy of the main container to Never."
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

--- Captured Logs ---
%s

--- Diagnostics ---
%s"""
