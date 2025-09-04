from fractale.agent.prompts import Prompt

recovery_prompt = f"""You are an expert AI workflow troubleshooter. A step in a workflow has failed and reached a maximum number of retries. THis could mean that we need to go back in the workflow and redo work. Your job is to analyze the error and recommend a single, corrective step. The steps, each associated with an agent, you can choose from are as follows:

Available Agents:
%s

The above is in the correct order, and ends on the agent that ran last with the failure (%s). The error message of the last step is the following:

%s

Your job is to analyze the error message to determine the root cause, and decide which agent is best suited to fix this specific error.
- You MUST formulate a JSON object for the corrective step with two keys: "agent_name" and "task_description".
- The new "task_description" MUST be a clear instruction for the agent to correct the specific error.
- You MUST only provide a single JSON object for the corrective step in your response.
- You MUST format your `task_description` to be a "You MUST" statement to the agent.
"""

# Same three inputs as above plus the unsuccessful attempt
recovery_error_prompt = recovery_prompt.strip() + " Your last attempt was not successful:\n%s"

retry_task = """You have had previous attempts, and here are summaries of previous issues:

{% for issue in issues %}
 - {{ issue }}
{% endfor %}
"""

retry_instructions = ["You MUST avoid making these errors again."]

persona = "You are manager of an agentic AI team."
retry_prompt = {
    "persona": persona,
    "context": "A step in your workflow has determined it cannot continue and returned to you.",
    "instructions": retry_instructions,
    "task": retry_task,
}


def get_retry_prompt(context, issues):
    """
    In testing, this should JUST be the error message.
    """
    # This is an impossible case - we would have appended the task descriptions if this is getting called
    # but you never know...
    if not issues:
        return ""
    return Prompt(retry_prompt, context).render({"issues": issues})
