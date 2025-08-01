def register(subparser):
    """
    Dynamically add agent parsers.
    """
    from . import get_agents

    for _, agent in get_agents().items():
        agent().add_arguments(subparser)
