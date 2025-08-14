retry_prompt = """You are a manager of LLM agents. A step in your plan has failed.
We are going to try again. Please prepare a prompt for the agent that includes instructions for a suggested fix. Here
is the original prompt given to this agent. Please use this to be mindful of the instructions that you provide back,
emphasizing points as needed:

%s

And here is the error that the agent received when trying to do the task.

%s

We want to streamline this fix, so please identify the error, and tweak the prompt so it is more succinct and directive to the agent.
Please return a response that speaks to the agent, and include your instruction for the fix, relevant parts of the error, and
why it is an error.
"""


def get_retry_prompt(instruction, prompt):
    """
    In testing, this should JUST be the error message.
    """
    return retry_prompt % (instruction, prompt)
