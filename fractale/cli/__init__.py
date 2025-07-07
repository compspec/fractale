#!/usr/bin/env python

import argparse
import os
import sys

from compspec.plugin.parser import plugin_registry
from compspec.plugin.registry import PluginRegistry

import fractale
import fractale.defaults as defaults
from fractale.logger import setup_logger

# Generate the plugin registry to add parsers
registry = PluginRegistry()
registry.discover()


def get_parser():
    parser = argparse.ArgumentParser(
        description="Fractale",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Global Variables
    parser.add_argument(
        "--debug",
        dest="debug",
        help="use verbose logging to debug.",
        default=False,
        action="store_true",
    )

    parser.add_argument(
        "--quiet",
        dest="quiet",
        help="suppress additional output.",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--config-dir",
        dest="config_dir",
        help="Fractale configuration directory to store subsystems. Defaults to ~/.fractale",
    )
    parser.add_argument(
        "--version",
        dest="version",
        help="show software version.",
        default=False,
        action="store_true",
    )

    subparsers = parser.add_subparsers(
        help="actions",
        title="actions",
        description="actions",
        dest="command",
    )
    subparsers.add_parser("version", description="show software version")

    # This will do the subsystem match before the run
    #    parser.add_argument("name", help="name of subsystem (required)")

    # Generate subsystem metadata for a cluster
    # fractale generate-subsystem --cluster A spack <args>
    generate = subparsers.add_parser(
        "generate",
        formatter_class=argparse.RawTextHelpFormatter,
        description="generate subsystem metadata for a cluster",
    )
    generate.add_argument("-c", "--cluster", help="cluster name")

    # Transform jobspecs from flux to Kubernetes (starting specific)
    transform = subparsers.add_parser(
        "transform",
        formatter_class=argparse.RawTextHelpFormatter,
        description="transform a jobspec",
    )
    transform.add_argument(
        "-t",
        "--to",
        dest="to_transformer",
        help="transform into this jobspec",
        default="kubernetes",
    )
    transform.add_argument(
        "-f", "--from", dest="from_transformer", help="transform from this jobspec", default="flux"
    )
    transform.add_argument(
        "--pretty",
        help="pretty print in the terminal",
        default=False,
        action="store_true",
    )

    # run.add_argument("-t", "--transform", help="transformer to use", default="flux")
    save = subparsers.add_parser(
        "save",
        formatter_class=argparse.RawTextHelpFormatter,
        description="save a picture of a subsystem graph",
    )
    save.add_argument("cluster", help="cluster to save")
    save.add_argument(
        "--subsystem", help="cluster to save (defaults to containment)", default="containment"
    )
    save.add_argument("--out", help="output file name")

    # This does just the user space subsystem match
    satisfy = subparsers.add_parser(
        "satisfy",
        formatter_class=argparse.RawTextHelpFormatter,
        description="determine clusters that satisfy a jobspec based on user subsystems",
    )
    # Generate a jobspec script
    script = subparsers.add_parser(
        "script",
        formatter_class=argparse.RawTextHelpFormatter,
        description="generate a batch script after satisfy",
    )
    script.add_argument(
        "--selector", help="selection algorithm to use", default="random", choices=["random"]
    )
    script.add_argument(
        "--transformer", help="transformer to use", default="flux", choices=["flux"]
    )
    for cmd in [satisfy, script, transform]:
        cmd.add_argument("jobspec", help="jobspec yaml or json file")

    for cmd in [satisfy, save, script]:
        cmd.add_argument(
            "--solver",
            help="subsystem solved backend",
            default=defaults.solver_backend_default,
            choices=defaults.solver_backends,
        )

    extractors = generate.add_subparsers(
        title="generate",
        description="Use compspec to extract specific application or environment metadata",
        dest="generate",
    )

    # Add plugin parsers to subsystem extractor / generator
    for _, plugin in registry.plugins.items():
        plugin.add_arguments(extractors)
    return parser


def run_fractale():
    """
    this is the main entrypoint.
    """
    parser = get_parser()

    def help(return_code=0):
        version = fractale.__version__

        print("\nFractale v%s" % version)
        parser.print_help()
        sys.exit(return_code)

    # If the user didn't provide any arguments, show the full help
    if len(sys.argv) == 1:
        help()

    # If an error occurs while parsing the arguments, the interpreter will exit with value 2
    args, extra = parser.parse_known_args()

    if args.debug is True:
        os.environ["MESSAGELEVEL"] = "DEBUG"

    # Show the version and exit
    if args.command == "version" or args.version:
        print(fractale.__version__)
        sys.exit(0)

    setup_logger(
        quiet=args.quiet,
        debug=args.debug,
    )

    # Here we can assume instantiated to get args
    if args.command == "generate":
        from .generate_subsystem import main
    elif args.command == "satisfy":
        from .satisfy import main
    elif args.command == "script":
        from .script import main
    elif args.command == "save":
        from .save import main
    elif args.command == "transform":
        from .transform import main
    else:
        help(1)
    global registry
    main(args, extra, registry=registry)


if __name__ == "__main__":
    run_fractale()
