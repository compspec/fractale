import os
import sys

from rich import print
from rich.panel import Panel
from rich.syntax import Syntax

from fractale.agent import get_agents


def main(args, extra, **kwargs):
    """
    Run an agent (do with caution!)
    """
    agents = get_agents()

    # Right now we only have a build agent :)
    if args.agent_name not in agents:
        sys.exit(f"{args.agent_name} is not a recognized agent.")

    # Get the agent and run!
    agent = agents[args.agent_name]()

    # This is built and tested! We can do something with it :)
    dockerfile = agent.run(args, extra)
    highlighted_syntax = Syntax(dockerfile, "docker", theme="monokai", line_numbers=True)
    print(
        Panel(
            highlighted_syntax,
            title="[bold green]✅ Final Dockerfile[/bold green]",
            border_style="green",
            expand=True,
        )
    )
