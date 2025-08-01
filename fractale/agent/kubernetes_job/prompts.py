regenerate_prompt = f"""Act as a Kubernetes job generator service expert. I am trying to write a YAML manifest for a Kubernetes Job in an environment for '%s' and the exact named application container `%s`. The previous attempt to generate the manifest failed. Here is the problematic manifest:

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
- The response should only contain the complete, corrected YAML manifest inside a single markdown code block.
- Use succinct comments to explain build logic and changes.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- This will be a final YAML manifest - do not tell me to customize something.
- Please deploy to the default namespace.
- Do not add resources, custom entrypoint/args, or securityContext unless explicitly told to.
"""


def get_regenerate_prompt(
    environment, container, template, dockerfile, error_message, no_pull=False
):
    prompt = regenerate_prompt % (environment, container, template, dockerfile, error_message)
    return add_no_pull(prompt, no_pull)


generate_prompt = f"""Act as a Kubernetes job generator service expert. I need to create a YAML manifest for a Kubernetes Job in an environment for '%s' for the exact container named '%s'.

Please generate a robust, production-ready manifest.
- Be mindful of the cloud and needs for resource requests and limits for network or devices.
- The response should ONLY contain the complete YAML manifest.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- This will be a final YAML manifest - do not tell me to customize something.
- Please deploy to the default namespace.
- Do not add resources, custom entrypoint/args, or securityContext unless explicitly told to.
"""


def get_generate_prompt(container, environment, no_pull=False):
    prompt = generate_prompt % (environment, container)
    return add_no_pull(prompt, no_pull=no_pull)


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
