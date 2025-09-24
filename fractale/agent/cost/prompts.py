from fractale.agent.prompts import Prompt

persona = "You are a cost estimation agent"
context = "We are selecting an instance type to minimize cost."
estimation_task = """Please read the application and environment needs and suggest an instance type that will minimize cost. You should account for application needs and estimated time to run, and the total accumulated instance cost.
{{instruction}}
"""

instructions = [
    "You MUST return a JSON list with one entry per result."
    "For each result, please include the 'application', 'environment', 'instance', 'type' (cpu or gpu), a 'reason' that explains your choice, and an 'estimate' with the estimated cost in USD."
    "If the application can use GPU, please suggest both types."
]

estimate_prompt = {
    "persona": persona,
    "context": context,
    "task": estimation_task,
    "instructions": instructions,
}


def get_estimation_prompt(context):
    """
    Since this is called by an agent, we can directly include requires as a param.
    (and not put it in the context).
    """
    instruction = context.get("instruction", required=True)
    return Prompt(estimate_prompt, context).render({"instruction": instruction})
