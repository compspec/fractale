from fractale.agent.prompts import Prompt

# Optimization Agent
persona = "You are a scaling study agent."
scaling_context = "You are running a scaling study for an application, and need to orchestrate execution at each size, a number of nodes."
scaling_instructions = [
    "You MUST return a JSON response with a 'decision' to PROCEED to the next size, or STOP the study along with a 'reason'",
    "You MUST stop the study after completing the last size OR when the application stops strong or weak scaling.",
    "You MUST provide an 'evidence' field that includes reference to work from the literature you are comparing your result to.",
    "When you stop, you MUST include a 'results field with the result at each size, and a 'summary' field of what you learned",
]

scaling_task = """You are running a scaling study across nodes and currently assessing results for size {{size}}. Next sizes to assess are: {{ sizes }}

Here are your instructions:
{{instructions}}

{% if attempts %}Here are current results from previous sizes:{% for size, fom in attempts.items() %}
 - Size {{ size }}: {{ fom }}
{% endfor %}{% endif %}
This run had the following configuration:
{{run_config}}
"""


scaling_prompt = {
    "persona": persona,
    "context": scaling_context,
    "instructions": scaling_instructions,
    "task": scaling_task,
}


# These are currently required, but don't necessarily have to be...
def get_scaling_prompt(context, run_config, best_fom):
    sizes = ", ".join([str(x) for x in context.sizes])
    return Prompt(scaling_prompt, context).render(
        {
            "instructions": context.scale,
            "size": context.size,
            "best_fom": best_fom,
            "attempts": context.get("scaling_attempts"),
            "run_config": run_config,
            "sizes": sizes,
        }
    )
