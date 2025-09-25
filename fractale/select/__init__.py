from .cost import CostSelection
from .random import RandomSelection

algorithms = {"random": RandomSelection, "agent-cost": CostSelection}


def get_selector(name):
    return algorithms.get(name)() or RandomSelection()
