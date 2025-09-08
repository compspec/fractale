from fractale.agent.prompts import Prompt
import fractale.agent.defaults as defaults

persona = "You are a Dockerfile build expert."
context = """
We are running experiments that deploy HPC applications to Kubernetes with tasks to build, deploy, and optimize
You are the agent responsible for the build step in that pipeline.
"""


# Requirements are specific to what the agent needs to do.
# for the build, not necessarily the format of the response.
requires = [
    "You MUST NOT change the name of the application container image provided.",
    "Don't worry about users/permissions - just be root.",
    "DO NOT forget to install certificates.",
    "Assume a default of CPU if GPU or CPU is not stated.",
    "Do NOT do a multi-stage build, and do NOT COPY or ADD anything.",
    "You MUST COPY executables to a system location to be on the PATH. Do NOT symlink",
    "You are only scoped to edit a Dockerfile to build the image.",
]

common_instructions = [
    "If the application involves MPI, configure it for compatibility for the containerized environment.",
    "The response should ONLY contain the complete Dockerfile.",
    'Do NOT add your narration unless it has a "#" prefix to indicate a comment.',
] + requires


rebuild_instructions = [
    "The response should only contain the complete, corrected Dockerfile inside a single markdown code block.",
    "Use succinct comments in the Dockerfile to explain build logic and changes.",
    "Follow the same guidelines as previously instructed.",
]
rebuild_task = """Your previous Dockerfile build has failed. Here is instruction for how to fix it.

Please analyze the instruction and your previous Dockerfile, and provide a corrected version.

{{instruction}}
"""

rebuild_prompt = {
    "persona": persona,
    "context": context,
    "task": rebuild_task,
    "instructions": rebuild_instructions + common_instructions,
}


def get_rebuild_prompt(context):
    """
    The rebuild prompt will either be the entire error output, or the parsed error
    output with help from the agent manager.
    """
    return Prompt(rebuild_prompt, context).render({"instruction": context.error_message})


build_instructions = [
    "The response should ONLY contain the complete Dockerfile.",
]

build_task = """I need to create a Dockerfile for an application '{{application}}'. The target environment is '{{environment}}'.

Please generate a robust, production-ready Dockerfile.
"""

# A structured data for prompts is assembled for each task
generate_prompt = {
    "persona": persona,
    "context": context,
    "task": build_task,
    "instructions": common_instructions + requires + build_instructions,
}


def get_build_prompt(context):
    environment = context.get("environment", defaults.environment)
    application = context.get("application", required=True)
    return Prompt(generate_prompt, context).render(
        {"application": application, "environment": environment}
    )
