from fractale.agent.prompts import Prompt

# Optimization Agent
persona = "You are a scaling study agent."
context = "You are running a scaling study for an application, and need to orchestrate execution at each size, a number of nodes."
scaling_instructions = [
    "You MUST return a JSON response with a 'decision' to RETRY, PROCEED to the next size, or STOP the study along with a 'reason'",
    "You MUST stop the study after completing the last size OR when the application stops strong or weak scaling.",
    "You MUST provide an 'evidence' field that includes reference to work you are comparing your result to.",
]

scaling_task = """You are running a scaling study, and currently working on size {{size}}.

Here are your instructions:

{{instructions}}

{% if previous_size %}{{previous_size}}{% end %}
"""


scaling_prompt = {
    "persona": persona,
    "context": context,
    "instructions": scaling_instructions,
    "task": scaling_task,
}


# These are currently required, but don't necessarily have to be...
def get_scaling_prompt(context):
    return Prompt(scaling_prompt, context).render({"instructions": context.requires})
