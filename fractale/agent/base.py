class Agent:
    """
    A base for an agent
    """

    # name and description should be on the class

    def add_arguments(self, subparser):
        """
        Add arguments for the agent to show up in argparse

        This is added by the plugin class
        """
        pass

    def run(self, args, extra):
        """
        Run the agent.
        """
        raise NotImplementedError(f"The {self.name} agent is missing a 'run' function")
