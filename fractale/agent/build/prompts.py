from fractale.agent.prompts import prompt_wrapper
import fractale.agent.defaults as defaults

# Requirements are provided to the manager to know how to prepare the context
requires = """I am a Dockerfile build agent. I accept the following inputs to be in my context:

dockerfile: (optional) If we are doing a rebuild, you should include the previously used
Dockerfile for me to iterate on. If it is the first time doing a build, you can leave this out.

application: (required) The name of the application that the Dockerfile container should build.

environment: (optional) The name of the expected environment to run the Dockerfile. If an environment
was previously provided, it should be included.

container: (optional) The name of the container to build. If one is not provided, it is OK, we will
default to a derivative of the application name. If a previously container name was provided, please
reuse it.
"""

common_instructions = """- Optimize for performance using best practices, especially for HPC applications.
- If the application involves MPI, configure it for compatibility for the containerized environment.
- The response should ONLY contain the complete Dockerfile.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- Do not change the name of the application image provided.
- Don't worry about users/permissions - just be root.
"""


# TODO: do we want to add back common instructions here?
rebuild_prompt = (
    f"""Your previous Dockerfile build has failed. Here is instruction for how to fix it.

Please analyze the instruction and your previous Dockerfile, and provide a corrected version.
- The response should only contain the complete, corrected Dockerfile inside a single markdown code block.
- Use succinct comments in the Dockerfile to explain build logic and changes. 
- Follow the same guidelines as previously instructed.

%s
"""
)


def get_rebuild_prompt(context):
    """
    The rebuild prompt will either be the entire error output, or the parsed error
    output with help from the agent manager.
    """
    return prompt_wrapper(rebuild_prompt % context.error_message, context=context)


build_prompt = (
    f"""Act as a Dockerfile builder service expert.
I need to create a Dockerfile for an application '%s'.
The target environment is '%s'.

Please generate a robust, production-ready Dockerfile.
- The response should ONLY contain the complete Dockerfile.
"""
    + common_instructions
)


def get_build_prompt(context):
    environment = context.get("environment", defaults.environment)
    application = context.get("application", required=True)
    return prompt_wrapper(build_prompt % (application, environment), context=context)
