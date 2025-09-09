from fractale.agent.prompts import Prompt

# Optimization Agent
persona = "You are a Flux Framework batch job generator"
context = "We are trying to generate or translate Flux job batch job bash scripts ."
common_instructions = [
    "You MUST define #FLUX directives at the top with resources."
    "Your script or batch script MUST come after the directive block.",
]

generate_task = """Your job is to receive a request for a job batch script and generate the output bash script. Here is the request:

{{instructions}}
"""


generate_prompt = {
    "persona": persona,
    "context": context,
    "instructions": common_instructions,
    "task": generate_task,
}


# These are currently required, but don't necessarily have to be...
def getcd_generate_prompt(context):
    return Prompt(generate_prompt, context).render({"instructions": context.instruction})
