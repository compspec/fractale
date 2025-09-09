#!/usr/bin/env python

import argparse
import sys

# This will pretty print all exceptions in rich
from fractale.transformer.flux.validate import Validator
import fractale.utils as utils

from rich.console import Console
from rich.panel import Panel
from rich.padding import Padding
from rich import box


def display_error(content, issue):
    """
    Displays a custom error message inside a red box.
    """
    console = Console(stderr=True)
    content = f"[bold]Here is the script:[/bold]\n" + content + "\n\n[red]" + issue + "[/red]"
    error_panel = Panel(
        Padding(f"{content}", (1, 2)),
        title="[bold white]Flux Batch Script Validation Failed[/bold white]",
        title_align="left",
        border_style="red",
        expand=False,
    )
    console.print(error_panel)



def get_parser():
    parser = argparse.ArgumentParser(
        description="Fractale Flux Validator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        help="actions",
        title="actions",
        description="actions",
        dest="command",
    )
    # Generate subsystem metadata for a cluster
    # fractale generate-subsystem --cluster A spack <args>
    validate = subparsers.add_parser(
        "validate",
        formatter_class=argparse.RawTextHelpFormatter,
        description="validate flux batch script",
    )
    validate.add_argument("path", help="path to batch.sh to validate")
    return parser


def run_validate():
    parser = get_parser()
    if len(sys.argv) == 1:
        help()

    # If an error occurs while parsing the arguments, the interpreter will exit with value 2
    args, _ = parser.parse_known_args()

    # Here we can assume instantiated to get args
    if args.command == "validate":
        return validate(args.path)
    raise ValueError(f"The command {args.command} is not known")


def validate(path):
    """
    Validate the path to a batch.sh or similar.
    """
    validator = Validator("batch")
    content = utils.read_file(path)
    try:
        # Setting fail fast to False means we will get ALL errors at once
        validator.parse(path, fail_fast=False)
    except Exception as e:
        display_error(content, str(e))
        sys.exit(1)

if __name__ == "__main__":
    run_validate()
