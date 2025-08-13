import fractale.agent.defaults as defaults

debug_prompt = f"""You are a debugging agent and expert. We attempted the following piece of code and had problems.
Please identify the error and advise for how to fix the error."""


def get_debug_prompt(context, requires):
    """
    Since this is called by an agent, we can directly include requires as a param.
    (and not put it in the context).
    """
    error_message = context.get("error_message", required=True)
    code_block = context.get("result", required=True)
    prompt = debug_prompt

    # Additional details from the user, e.g., about data
    details = context.get("details")
    if details:
        prompt += "\nPlease consider the follow details from the user:\n%s\n" % details

    # Requirements are specific constraints to give to the error agent
    if requires:
        prompt += "\n" + requires + "\n"

    # Add additional context
    prompt += "Here is additional context to guide your instruction:\n"
    for key, value in context.items():
        if key in defaults.shared_args:
            continue
        prompt += f"{key} is defined as: {value}\n"

    prompt += f"Here is the code:\n{code_block}\nAnd here is the error output:\n{error_message}"
    return prompt
