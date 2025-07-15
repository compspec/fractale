import re
import shlex
from datetime import datetime, timedelta

from fractale.logger.generate import JobNamer
from fractale.transformer.base import Script, TransformerBase
from fractale.transformer.common import JobSpec


class CobaltScript(Script):
    """
    A helper class for Cobalt. Unused as Cobalt uses command-line flags.
    """

    def __init__(self):
        self.script_lines = ["#!/bin/bash"]
        self.directive = ""  # No directive prefix


def priority_to_cobalt_priority(priority_str):
    """
    Cobalt does not typically expose a direct user-facing priority flag.
    This is handled by queue policies. This function is a no-op.
    """
    return None


def cobalt_priority_to_priority(cobalt_priority):
    """
    Cobalt does not have a parsable priority flag, so this always returns normal.
    """
    return "normal"


def seconds_to_cobalt_walltime(total_seconds):
    """
    Converts integer seconds to Cobalt's HH:MM:SS walltime format.
    Cobalt -t flag also accepts minutes directly, but HH:MM:SS is more explicit.
    """
    if not isinstance(total_seconds, int) or total_seconds <= 0:
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"


def cobalt_walltime_to_seconds(time_str):
    """
    Converts Cobalt HH:MM:SS walltime string back to integer seconds.
    """
    if not time_str:
        return None
    try:
        # Can be HH:MM:SS or just minutes
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())
        elif len(parts) == 1:
            return int(parts[0]) * 60
        return None
    except (ValueError, IndexError):
        return None


def epoch_to_cobalt_begin_time(epoch_seconds):
    """
    Converts Unix epoch to Cobalt's begin time format for the '--at' flag.
    """
    if not isinstance(epoch_seconds, int) or epoch_seconds <= 0:
        return None
    # A common supported format is YYYY-MM-DDTHH:MM:SS
    return datetime.fromtimestamp(epoch_seconds).strftime("%Y-%m-%dT%H:%M:%S")


def cobalt_begin_time_to_epoch(time_str):
    """
    Converts a Cobalt begin time string back to Unix epoch.
    """
    if not time_str:
        return None
    try:
        return int(datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S").timestamp())
    except (ValueError, IndexError):
        return None


def parse_cobalt_command(command_lines, spec):
    """
    Parses a command line from within a Cobalt script body.
    """
    if not command_lines:
        return []

    main_command = command_lines[-1]
    parts = shlex.split(main_command)

    # The common launcher on ALCF systems is 'aprun'
    if parts and parts[0] in ("aprun"):
        parts = parts[1:]

    if parts and parts[0] in ("singularity", "apptainer") and parts[1] == "exec":
        spec.container_image = parts[2]
        parts = parts[3:]

    return parts


class CobaltTransformer(TransformerBase):
    """
    Transforms a JobSpec to/from a Cobalt submission script.
    Note: Cobalt uses command-line flags to qsub, not in-script directives.
    This transformer generates a "runner" script that calls qsub.
    """

    def convert(self, spec):
        """
        Converts a JobSpec into a self-submitting Cobalt script string.
        """
        job_name = spec.job_name or JobNamer().generate()

        # Build the qsub command line
        qsub_cmd = ["qsub"]
        qsub_cmd.extend(["-A", spec.account] if spec.account else [])
        qsub_cmd.extend(["-q", spec.queue] if spec.queue else [])
        qsub_cmd.extend(["-n", str(spec.num_nodes)])

        # Cobalt uses --proccount for total MPI ranks
        if spec.num_tasks > 1:
            qsub_cmd.extend([f"--proccount", str(spec.num_tasks)])

        wt = seconds_to_cobalt_walltime(spec.wall_time)
        if wt:
            qsub_cmd.extend(["-t", wt])

        bt = epoch_to_cobalt_begin_time(spec.begin_time)
        if bt:
            qsub_cmd.extend(["--at", bt])

        # -O sets the prefix for output/error files
        qsub_cmd.extend(["-O", job_name])

        if spec.environment:
            for k, v in spec.environment.items():
                qsub_cmd.extend(["--env", f"{k}={v}"])

        # Build the script that will be executed on the compute node
        exec_script_parts = ["#!/bin/bash", ""]

        # The common launcher for Cobalt is aprun
        aprun_cmd = ["aprun"]

        # Match aprun geometry to qsub submission
        aprun_cmd.extend(["-n", str(spec.num_tasks)])
        aprun_cmd.extend(["-N", str(spec.cpus_per_task)])

        if spec.container_image:
            aprun_cmd.extend(["singularity", "exec", spec.container_image])
        if spec.executable:
            aprun_cmd.append(spec.executable)
        if spec.arguments:
            aprun_cmd.extend(spec.arguments)

        exec_script_parts.append(" ".join(aprun_cmd))
        exec_script = "\n".join(exec_script_parts)

        # Combine into a self-submitting script using a "here document"
        runner_script = ["#!/bin/bash", " ".join(qsub_cmd) + " << EOF", exec_script, "EOF"]
        return "\n".join(runner_script)

    def _parse(self, content, return_unhandled=False):
        """
        Parses a self-submitting Cobalt script into a JobSpec.
        """
        spec = JobSpec()
        not_handled = set()

        # Find the qsub line and the script body
        qsub_line = ""
        script_body = []
        in_script_body = False

        qsub_re = re.compile(r"qsub\s+(.+?)<<\s*EOF")

        for line in content.splitlines():
            m = qsub_re.search(line)
            if m:
                qsub_line = m.group(1)
                in_script_body = True
                continue

            if in_script_body and line.strip() != "EOF":
                script_body.append(line)

        # Parse the qsub command line flags
        if qsub_line:
            args = shlex.split(qsub_line)
            i = 0
            while i < len(args):
                arg = args[i]
                val = args[i + 1] if i + 1 < len(args) else ""

                if arg == "-A":
                    spec.account = val
                    i += 2
                elif arg == "-q":
                    spec.queue = val
                    i += 2
                elif arg == "-n":
                    spec.num_nodes = int(val)
                    i += 2
                elif arg == "-t":
                    spec.wall_time = cobalt_walltime_to_seconds(val)
                    i += 2
                elif arg == "--proccount":
                    spec.num_tasks = int(val)
                    i += 2
                elif arg == "-O":
                    spec.job_name = val
                    i += 2
                elif arg == "--at":
                    spec.begin_time = cobalt_begin_time_to_epoch(val)
                    i += 2
                else:
                    not_handled.add(arg)
                    i += 1

        # We again assume a block of text here.
        spec.script = script_body

        # Parse the execution command from the script body
        parts = parse_cobalt_command(spec.script, spec)
        if parts:
            # Need to parse aprun args to get cpus_per_task
            temp_args = parts.copy()
            if "-N" in temp_args:
                idx = temp_args.index("-N")
                spec.cpus_per_task = int(temp_args[idx + 1])
                temp_args.pop(idx)
                temp_args.pop(idx)

            spec.executable = temp_args[0]
            spec.arguments = temp_args[1:]

        if return_unhandled:
            return not_handled
        return spec
