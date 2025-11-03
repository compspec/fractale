#!/usr/bin/env python

import argparse
import json
import sys

import yaml
from flux.job.Jobspec import validate_jobspec
from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel

import fractale.utils as utils

# This will pretty print all exceptions in rich
from fractale.transformer.flux.validate import Validator


def display_error(content, issue):
    """
    Displays a custom error message inside a red box.
    """
    console = Console(stderr=True)
    content = (
        f"[bold]Flux Batch Validation Failed:[/bold]\n[yellow]"
        + content
        + "[/yellow]\n\n[red]"
        + issue
        + "[/red]"
    )
    console.print(content)


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

    count = subparsers.add_parser(
        "count",
        formatter_class=argparse.RawTextHelpFormatter,
        description="count resources in flux batch script",
    )
    count.add_argument("path", help="path to batch.yaml to count resources")
    return parser


def run_command():
    parser = get_parser()
    if len(sys.argv) == 1:
        help()

    # If an error occurs while parsing the arguments, the interpreter will exit with value 2
    args, _ = parser.parse_known_args()

    # Here we can assume instantiated to get args
    if args.command == "validate":
        return validate(args.path)
    elif args.command == "count":
        return count_resources(args.path)
    raise ValueError(f"The command {args.command} is not known")


def validate(path):
    """
    Validate a batch.sh, jobspec.yaml, or jobspec.json.
    """
    jobspec = None
    content = utils.read_file(path)
    yaml_content = yaml.safe_load(content)
    json_content = json.dumps(yaml_content)
    if not isinstance(yaml_content, dict):
        validator = Validator("batch")
        try:
            # Setting fail fast to False means we will get ALL errors at once
            validator.validate(path, fail_fast=False)
        except Exception as e:
            display_error(content, str(e))
            sys.exit(1)
    else:
        try:
            jobspec = validate_jobspec(json_content)
        except Exception as e:
            display_error(content, str(e))
            sys.exit(1)
    return jobspec


def count_resources(path):
    """
    Count the resources in a jobspec.yaml or similar.
    """
    jobspec = validate(path)
    if jobspec is not None:
        print(
            "The jobspec is valid! Here are the total resource"
            " counts per type requested by the provided jobspec:"
        )
        for res in jobspec[1].resource_walk():
            print(f"Type: {res[1]['type']}, count: {res[2]}")


if __name__ == "__main__":
    run_command()
