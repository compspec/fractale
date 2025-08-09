import fractale.utils as utils
import json
import os
import re
import tempfile

class Step:
    def __init__(self, step):
        self.step = step

    @property
    def agent(self):
        return self.get("agent")

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
