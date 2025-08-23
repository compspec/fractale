import fractale.agent.defaults as defaults
from fractale.agent.prompts import prompt_wrapper

# TODO should this be allowed to return to a different agent?
common_instructions = """
- You can make changes to the application execution only.
- You are not allowed to request changes to any configuration beyond the application execution command.
"""

optimize_prompt = f"""You are an optimization agent. Your job is to receive application commands and environments, and make a suggestion for how to improve a metric of interest.
Here are your instructions:

%s

- The response should ONLY contain parameters for resources cpu, memory, nodes, and environment variables, formatting as a JSON string that can be parsed.
"""

# This is added to details from a job manager optimization prompt about the decision that should come back.
supplement_optimize_prompt = """You also need to decide if the job is worth retrying again. You have made %s attempts and here are the figure of merits as described for those attempts:
%s
Please include in your response a "decision" field that is RETRY or STOP. You should keep retrying until you determine the application run is optimized. If you like, you can add a "reason" field that briefly summarizes the decision.
"""


# These are currently required, but don't necessarily have to be...
def get_optimize_prompt(context):
    return optimize_prompt % context.requires
