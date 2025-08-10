import jsonschema
from jsonschema import validators
from rich import print

import fractale.utils as utils


def set_defaults(validator, properties, instance, schema):
    """
    Fill in default values (agent goal)
    """
    for prop, sub_schema in properties.items():
        if "default" in sub_schema:
            instance.setdefault(prop, sub_schema["default"])


# This extends default validators to set defaults
plan_validator = validators.extend(
    jsonschema.Draft7Validator,
    {"properties": set_defaults},
)

plan_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "goal": {"type": "string", "default": "Use provided agents to finish the plan"},
        "plan": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "context": {
                        "type": "object",
                        # We don't need to validate the contents of the context
                        # but we could add more rules here if needed.
                        "additionalProperties": True,
                    },
                },
                "required": ["agent"],
            },
        },
    },
    "required": ["name", "plan"],
}


class Plan:
    """
    A plan for a manager includes one or more agents and a goal.
    """

    def __init__(self, plan_path):
        self.plan_path = plan_path
        self.plan = utils.read_yaml(plan_path)
        self.agent_names = set()

        self.validate()
        self.load()

    def load(self):
        """
        Load a manager plan into agent steps.
        """
        from fractale.agent import get_agents

        known_agents = get_agents()

        print(f"Loading plan from [bold magenta]{self.plan_path}[/bold magenta]...")
        self.agents = []
        for spec in self.plan.get("plan", []):
            agent_name = spec["agent"]
            if agent_name not in known_agents:
                raise ValueError(f"Agent {spec['agent']} is not known.")

            # Add the agent to the step
            step = Step(spec, known_agents[agent_name])

            # The agents are retrieved via index
            self.agents.append(step)

            # For now we are requiring step names to be unique
            # This can change, but we do this because we find the step
            # index later when in recovery mode.
            if agent_name in self.agent_names:
                raise ValueError("Repeated agent detected, not supported yet.")
            self.agent_names.add(agent_name)

    def __len__(self):
        return len(self.plan["plan"])

    def validate(self):
        """
        Validate the plan structure.
        """
        validator = plan_validator(plan_schema)
        try:
            # The validate function will check rules and apply defaults, modified in place
            validator.validate(self.plan)
            print("✅ Plan is valid and has been updated with defaults.")
        except Exception as e:
            raise ValueError(f"❌ Plan is invalid: {e}!")

    def __getitem__(self, key):
        """
        Allows indexing (e.g., plan[0]) to get steps.
        """
        return self.agents[key]


class Step:
    def __init__(self, step, agent):
        self.step = step
        self._agent = agent()

        # If the step context defines a max number of attempts, set it for the agent
        max_attempts = self.step["context"].get("max_attempts")
        self._agent.set_max_attempts(max_attempts)

    def update(self, context):
        """
        Carefully add only new attributes.

        We can't use dict tricks here because we lose the context class.
        """
        for k, v in self.step["context"].items():
            if k not in context:
                context[k] = v
        return context

    def execute(self, context):
        """
        Execute a plan step (associated with an agent)
        """
        # Add new variables that aren't present
        context = self.update(context)

        # TODO allow adding limit for attempts
        # right now this only returns after success
        # This is the context returned
        return self._agent.run(context)

    @property
    def agent(self):
        return self.get("agent")

    @property
    def context(self):
        return self.get("context")

    # STOPPED HERE:
    # each of the step and the manager have a context. We need to update at some
    # point so there is one context. It isn't clear if the manager should do this
    # and then carry forward logic to a subsequent step, or something else.

    @property
    def attempts(self):
        return self.get("attempts")

    @property
    def description(self):
        return self.get("description", f"This is a {self.agent} agent.")

    def reached_maximum_attempts(self, attempts):
        """
        Determine if we have reached maximum attempts for the step.
        """
        if self.attempts is None:
            return False
        if self.attempts > attempts:
            return True
        return False

    def get(self, name, default=None):
        return self.step.get(name) or default
