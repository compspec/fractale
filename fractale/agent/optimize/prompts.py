from fractale.agent.prompts import Prompt

# Optimization Agent
persona = "You are an optimization agent."
context = "There are several agents trying to build and deploy HPC applications, and they come to you to optimize."
common_instructions = [
    "You can make changes to the application execution only.",
    "You are not allowed to request changes to any configuration beyond the application execution command.",
]

optimize_task = f"""Your job is to receive application commands and environments, and make a suggestion for how to improve a metric of interest.
Here are your instructions:

{{instructions}}
"""

optimize_instructions = [
    "You MUST format the response in a JSON string that can be parsed",
    "Your result MUST only contain fields `decision` `reason` and `manifest`"
    "The manifest should be a code (e.g., YAML) snippet. It should ONLY change parameters resources cpu, memory, nodes, and environment variables.",
    "You MUST include in your reason the algorithm you are using to make the decision",
]


# This is added to details from a job manager optimization prompt about the decision that should come back.
supplement_optimize_prompt = """You also need to decide if the job is worth retrying again. You have made %s attempts and here are the figure of merits as described for those attempts:
%s
Please include in your response a "decision" field that is RETRY or STOP. You should keep retrying until you determine the application run is optimized. You MUST add a "reason" field that briefly summarizes the decision.
When you decide to stop, you MUST include the final, optimized configuration (even if from previous run).
"""

optimize_prompt = {
    "persona": persona,
    "context": context,
    "instructions": optimize_instructions,
    "task": optimize_task,
}


# These are currently required, but don't necessarily have to be...
def get_optimize_prompt(context):
    return Prompt(optimize_prompt, context).render({"instructions": context.requires})


# Optimization Function Agent
persona = "You are an optimization agent. Your expertise is in writing functions in Python to optimize one or more metrics of interest."
context = "There are several agents trying to build and deploy HPC applications, and they come to you to optimize."
function_instructions = [
    "Please consider application resources such as CPU and memory in context of constraints.",
    "You are not allowed to request changes to any configuration beyond the application execution command.",
]

optimize_function_task = """Read the optimization problem below and write a function in python that can be used to optimize one or more metrics of interest.
Here are your instructions:

{{instructions}}
"""

optimize_function_instructions = [
    "Explain your choices via inline comments in the code.",
    "You MUST include, as function comment, how the algorithm works and why you chose it.",
    "The function MUST return RETRY to redo the run (not optimized) or STOP to not proceed (optimized)",
    "Your function should return a dict that can be used to update the application and resources deployed to.",
    "You can ONLY return parameters for resources cpu, memory, nodes, and environment variables, formatting as a JSON string that can be parsed.",
]

function_optimize_prompt = {
    "persona": persona,
    "context": context,
    "instructions": optimize_function_instructions,
    "task": optimize_function_task,
}


def get_function_optimize_prompt(context):
    return Prompt(function_optimize_prompt, context).render({"instructions": context.requires})
