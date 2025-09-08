import fractale.agent.defaults as defaults
from fractale.agent.prompts import Prompt

persona = "You are a debugging agent and expert."
context = "We attempted the following piece of code and had problems."
debug_task = """Please identify the error and advise for how to fix it. The agent you are returning to can only make scoped changes, which we provide below. {% if return_to_manager %}If you determine the issue cannot be resolved by changing one of these files, we will need to return to another agent. In this case, please provide "RETURN TO MANAGER" anywhere in your response.{% endif %}
If you would like a human to add comment to how to address the issue, put "RETURN TO HUMAN" anywhere in your response and include any questions you have about the issue. You can ONLY choose one source of help.
{% if requires %}{% for item in requires %}  - {{item}}\n{% endfor %}{% endif %}
Here is additional context to guide your instruction. YOU CANNOT CHANGE THESE VARIABLES OR FILES OR SUGGEST TO DO SO.
  {{ context }}
Here is the code:\n{{code_block}}\nAnd here is the error output:\n{{error_message}}
"""

debug_prompt = {
    "persona": persona,
    "context": context,
    "task": debug_task,
    "instructions": [],
}


def get_debug_prompt(context, requires):
    """
    Since this is called by an agent, we can directly include requires as a param.
    (and not put it in the context).
    """
    error_message = context.get("error_message", required=True)
    code_block = context.get("result", required=True)

    # Prepare additional context
    additional_context = ""
    for key, value in context.items():
        if key in defaults.shared_args:
            continue
        if key == "details":
            key = "details from user"
        additional_context += f"{key} is defined as: {value}\n"
    return Prompt(debug_prompt, context).render(
        {
            "error_message": error_message,
            # Return to manager MUST be False
            "return_to_manager": context.get("return_to_manager") is not False,
            "requires": requires,
            "context": additional_context,
            "code_block": code_block,
        }
    )
