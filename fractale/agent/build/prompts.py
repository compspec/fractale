from fractale.agent.prompts import prompt_wrapper
import fractale.agent.defaults as defaults

# Requirements are specific to what the agent needs to do.
# for the build, not necessarily the format of the response.
requires = """
- Do not change the name of the application image provided.
- Don't worry about users/permissions - just be root.
- Assume a default of CPU if GPU or CPU is not stated.
- Do not do a multi-stage build, and do not COPY or ADD anything.
- Try to place executables on the PATH so they do not need to be discovered.
- You are only scoped to edit a Dockerfile to build the image.
"""

common_instructions = (
    """- If the application involves MPI, configure it for compatibility for the containerized environment.
- The response should ONLY contain the complete Dockerfile.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
"""
    + requires
)

# TODO: do we want to add back common instructions here?
rebuild_prompt = f"""Your previous Dockerfile build has failed. Here is instruction for how to fix it.

Please analyze the instruction and your previous Dockerfile, and provide a corrected version.
- The response should only contain the complete, corrected Dockerfile inside a single markdown code block.
- Use succinct comments in the Dockerfile to explain build logic and changes.
- Follow the same guidelines as previously instructed.

%s
"""


def get_rebuild_prompt(context):
    """
    The rebuild prompt will either be the entire error output, or the parsed error
    output with help from the agent manager.
    """
    return prompt_wrapper(rebuild_prompt % context.error_message, context=context)


build_prompt = (
    f"""Act as a Dockerfile builder service expert. I need to create a Dockerfile for an application '%s'. The target environment is '%s'.

Please generate a robust, production-ready Dockerfile.
- The response should ONLY contain the complete Dockerfile.
"""
    + common_instructions
)


def get_build_prompt(context):
    environment = context.get("environment", defaults.environment)
    application = context.get("application", required=True)
    return prompt_wrapper(build_prompt % (application, environment), context=context)
