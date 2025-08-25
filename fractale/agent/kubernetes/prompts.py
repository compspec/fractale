common_instructions = """- Be mindful of the cloud and needs for resource requests and limits for network or devices.
- The response should only contain the complete, corrected YAML manifest inside a single markdown code block.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- Use succinct comments to explain build logic and changes.
- This will be a final YAML manifest - do not tell me to customize something.
"""

common_requires = """
- Please deploy to the default namespace.
- Do not create or require external data. Use example data provided with the app or follow instructions.
- Do not add resources, custom entrypoint/args, affinity, init containers, nodeSelector, or securityContext unless explicitly told to.
- Do NOT add resource requests or limits. The pod should be able to use the full available resources and be Burstable.
- Assume that needed software is on the PATH, and don't specify full paths to executables.
- Keep in mind that an instance vCPU == 1 logical CPU. Apps typically care about logical CPU.
"""

regenerate_prompt = """Your previous attempt to generate the manifest failed. Please analyze the instruction to fix it and make another try.

%s
"""
