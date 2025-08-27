common_context = """
We are running experiments that deploy HPC applications to Kubernetes with tasks to build, deploy, and optimize
You are the agent responsible for the deploy step in that pipeline.
"""

common_instructions = [
    "The response should ONLY contain a complete YAML manifest inside a single markdown code block.",
    'You MUST NOT add your narration unless it has a "#" prefix to indicate a comment.',
    "Use succinct comments to explain build logic and changes.",
    "This MUST be a final YAML manifest - do NOT ask for customization.",
]

common_requires = [
    "Deploy to the default namespace.",
    "You MUST NOT create or require external data. Use example data provided with the app or follow instructions.",
    "You MUST NOT add custom entrypoint/args, affinity, init containers, nodeSelector, or securityContext unless explicitly told to.",
    "You MUST NOT add resource requests or limits. The pod should be able to use the full available resources and be Burstable.",
    "You SHOULD assume that needed software is on the PATH, and don't specify full paths to executables.",
    "Keep in mind that an instance vCPU == 1 logical CPU. Apps typically care about logical CPU.",
]

regenerate_task = """Your previous attempt to generate the manifest failed. Please analyze the instruction to fix it and make another try. {{testing}}

{{task}}
"""
