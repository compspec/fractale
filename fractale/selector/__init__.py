import fractale.selector.algorithms as algorithms

plugins = {"random": algorithms.random_selection}


def get_selector(name):
    if name not in plugins:
        raise ValueError(f"{name} is not a valid selection algorithm.")
    return plugins[name]
