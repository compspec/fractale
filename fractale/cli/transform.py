#!/usr/bin/env python

import os
import sys

import yaml
from rich import print
from rich.pretty import pprint

from fractale.transformer import detect_transformer, get_transformer


def main(args, extra, **kwargs):
    """
    Transform between jobspecs.
    """
    # The jobspec needs to exist as a file here
    if not os.path.exists(args.jobspec):
        sys.exit(f"JobSpec {args.jobspec} does not exist.")

    # If no from transformer defined, try to detect
    if args.from_transformer is None:
        args.from_transformer = detect_transformer(args.jobspec)

    # No selector or solver, just manual transform
    from_transformer = get_transformer(args.from_transformer)
    to_transformer = get_transformer(args.to_transformer)

    # Parse the jobspec to transform from
    normalized_jobspec = from_transformer.parse(args.jobspec)
    final_jobspec = to_transformer.convert(normalized_jobspec)

    if args.pretty and args.to_transformer in ["slurm"]:
        print(final_jobspec)
    elif args.pretty:
        pprint(final_jobspec, indent_guides=True)
    elif args.to_transformer in ["kubernetes"]:
        yaml.dump(final_jobspec, sys.stdout, sort_keys=True, default_flow_style=False)
    else:
        print(final_jobspec)
