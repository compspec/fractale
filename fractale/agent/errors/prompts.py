import fractale.agent.defaults as defaults

debug_prompt = f"""You are a debugging agent and expert. We attempted the following piece of code and had problems.
Please identify the error and advise for how to fix the error. The agent you are returning to can only make scoped
changes, which we provide below. If you determine the issue cannot be resolved by changing one of these files,
we will need to return to another agent. In this case, please provide "RETURN TO MANAGER" anywhere in your response.
"""

interactive_prompt = """  If there is information the step cannot know such as runtime parameters or data paths"
and the fix is not obvious (and you are guessing) please provide "INTERACTIVE SESSION" anywhere in your response
"""


def get_debug_prompt(context, requires):
    """
    Since this is called by an agent, we can directly include requires as a param.
    (and not put it in the context).
    """
    error_message = context.get("error_message", required=True)
    code_block = context.get("result", required=True)
    prompt = debug_prompt

    if context.get("allow_interactive") is True:
        prompt += interactive_prompt

    # Requirements are specific constraints to give to the error agent
    if requires:
        prompt += requires + "\n"

    # Add additional context (details from user are provided here)
    prompt += "Here is additional context to guide your instruction. YOU CANNOT CHANGE THESE VARIABLES OR FILES OR SUGGEST TO DO SO.\n"
    for key, value in context.items():
        if key in defaults.shared_args:
            continue
        if key == "details":
            key = "details from user"
        prompt += f"{key} is defined as: {value}\n"

    prompt += f"Here is the code:\n{code_block}\nAnd here is the error output:\n{error_message}"
    # Remove double newlines
    return prompt.strip("\n\n")
