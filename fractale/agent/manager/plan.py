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

    def __init__(self, plan_path, use_cache=False, save_incremental=False):
        self.plan_path = plan_path
        self.plan = utils.read_yaml(plan_path)
        self.agent_names = set()
        self.use_cache = use_cache
        self.save_incremental = save_incremental

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
            step = Step(
                spec,
                known_agents[agent_name],
                use_cache=self.use_cache,
                save_incremental=self.save_incremental,
            )

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
    """
    A step is a simple abstraction to hold an agent and a plan.

    It could be unecessary, but I am keeping for now.
    """

    def __init__(self, step, agent, use_cache=False, save_incremental=False):
        self.step = step

        # If the step context defines a max number of attempts, set it for the agent
        max_attempts = self.step["context"].get("max_attempts")
        self._agent = agent(
            use_cache=use_cache, save_incremental=save_incremental, max_attempts=max_attempts
        )

    def logs(self):
        """
        Courtesy function to expose agent logs.
        """
        return self._agent.metadata

    def update(self, context):
        """
        Carefully add only new attributes, unless it's a step-specific attribute we
        know is shared but unique to steps.

        We can't use dict tricks here because we lose the context class.
        """
        overrides = ["agent_name", "details", "use_cache", "outfile"]
        for k, v in self.step["context"].items():
            if k not in context or k in overrides:
                context[k] = v
        return context

    def execute(self, context):
        """
        Execute a plan step (associated with an agent)
        """
        # Add new variables that aren't present
        context = self.update(context)

        # This is the context returned
        return self._agent.run(context)

    def mark_retry(self):
        """
        A function to mark that the entire plan was retried.
        """
        self._agent.metadata["counts"]["retries"] += 1

    @property
    def agent(self):
        return self.get("agent")

    @property
    def attempts(self):
        return self._agent.attempts

    @property
    def context(self):
        return self.get("context")

    def reset_context(
        self,
        context,
    ):
        return self._agent.reset_context(context)

    @property
    def description(self):
        return self.get("description", f"This is a {self.agent} agent.")

    def get(self, name, default=None):
        return self.step.get(name) or default
