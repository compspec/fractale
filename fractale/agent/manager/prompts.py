recovery_prompt = f"""You are an expert AI workflow troubleshooter. A step in a workflow has failed and reached a maximum number of retries. THis could mean that we need to go back in the workflow and redo work. Your job is to analyze the error and recommend a single, corrective step. The steps, each associated with an agent, you can choose from are as follows:

Available Agents:
%s

The above is in the correct order, and ends on the agent that ran last with the failure (%s). The error message of the last step is the following:

%s

Your job is to analyze the error message to determine the root cause, and decide which agent is best suited to fix this specific error. Formulate a JSON object for the corrective step with two keys: "agent_name" and "task_description".  The new "task_description" MUST be a clear instruction for the agent to correct the specific error. Provide only the single JSON object for the corrective step in your response.
"""

recovery_error_prompt = recovery_prompt.strip() + " Your first attempt was not successful:\n%s"

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
