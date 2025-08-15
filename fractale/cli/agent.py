import sys

from fractale.agent import get_agents


def main(args, extra, **kwargs):
    """
    Run an agent (do with caution!)
    """
    agents = get_agents()

    # If we have a plan, we run the manager.
    if args.plan is not None:
        args.agent_name = "manager"

    # Right now we only have a build agent :)
    if args.agent_name not in agents:
        sys.exit(f"{args.agent_name} is not a recognized agent.")

    # Get the agent and run!
    # - results determines if we want to save state to an output directory
    # - save_incremental will add a metadata section
    # - max_attempts is for the manager agent (defaults to 10)
    agent = agents[args.agent_name](
        use_cache=args.use_cache,
        results_dir=args.results,
        save_incremental=args.incremental,
        max_attempts=args.max_attempts,
    )

    # This is the context - we can remove variables not needed
    context = vars(args)
    del context["use_cache"]

    # This is built and tested! We can do something with it :)
    # Note that vars converts the argparse arguments into a dictionary
    agent.run(context)
