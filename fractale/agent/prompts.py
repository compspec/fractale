import copy

from jinja2 import Template

template = """
    Persona:
    {{persona}}

    {% if context %}Context: {{context|trim}}{% endif %}

    Task: {{task|trim}}

    {% if instructions %}Instructions & Constraints:
    {% for line in instructions %}{{line}}
    {% endfor %}{% endif %}
"""


class Prompt:
    """
    A prompt is a structured instruction for an LLM.
    We attempt to define the persona, context, task, audience, instructions, and constraints.
    Data sections should use words MUST, MUST NOT, AVOID, ENSURE
    """

    def __init__(self, data, context):
        """
        This currently assumes setting a consistent context for one generation.
        If that isn't the case, context should be provided in the function below.
        """
        self.data = data
        self.context = context

    def render(self, kwargs):
        """
        Render the final user task, and then the full prompt.
        """
        # The kwargs are rendered into task
        render = copy.deepcopy(self.data)

        # Do we have additional details for instrucitons?
        try:
            render["instructions"] += (self.context.get("details") or "").split("\n")
        except:
            print("ISSUE WITH RENDER IN GENERIC PROMPTS")
            import IPython

            IPython.embed()
        render["task"] = Template(self.data["task"]).render(**kwargs)
        prompt = Template(template).render(**render)
        return prompt
