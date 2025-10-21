from .random import RandomSelection

algorithms = {"random": RandomSelection}

# These require genai
try:
    import google.generativeai as genai

    from .cost import CostSelection

    algorithms["agent-cost"] = CostSelection
except ImportError:
    pass


def get_selector(name):
    return algorithms.get(name)() or RandomSelection()
