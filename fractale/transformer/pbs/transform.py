import re
import shlex
from datetime import datetime, timedelta

from fractale.transformer.base import Script, TransformerBase
from fractale.transformer.common import JobSpec


class PBSScript(Script):
    """
    A helper class to build a PBS batch script line by line.
    """

    def __init__(self):
        self.script_lines = ["#!/bin/bash"]
        self.directive = "#PBS"


def priority_to_pbs_priority(priority_str):
    """
    Maps a semantic string to a PBS priority value (-1024 to 1023).
    """
    # Higher value means HIGHER priority in PBS.
    return {
        "low": -500,
        "normal": 0,
        "high": 500,
        "urgent": 1000,
    }.get(priority_str, 0)


def pbs_priority_to_priority(pbs_priority):
    """
    Maps a PBS priority value back to a semantic string.
    """
    if pbs_priority is None:
        return "normal"
    if pbs_priority < 0:
        return "low"
    if pbs_priority == 0:
        return "normal"
    if 0 < pbs_priority < 1000:
        return "high"
    return "urgent"  # for pbs_priority >= 1000


def seconds_to_pbs(total_seconds):
    """
    Converts integer seconds to PBS HH:MM:SS walltime format.
    """
    if not isinstance(total_seconds, int) or total_seconds <= 0:
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"


def pbs_time_to_seconds(time_str):
    """
    Converts PBS HH:MM:SS walltime string back to integer seconds.
    """
    if not time_str:
        return None
    h, m, s = map(int, time_str.split(":"))
    return int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())


def epoch_to_pbs_begin_time(epoch_seconds):
    """
    Converts Unix epoch to PBS packed date-time format for the '-a' flag.
    """
    if not isinstance(epoch_seconds, int) or epoch_seconds <= 0:
        return None
    return datetime.fromtimestamp(epoch_seconds).strftime("%Y%m%d%H%M.%S")


def pbs_begin_time_to_epoch(time_str):
    """
    Converts a PBS packed date-time string back to Unix epoch.
    """
    if not time_str:
        return None
    try:
        # Handle with and without seconds
        fmt = "%Y%m%d%H%M.%S" if "." in time_str else "%Y%m%d%H%M"
        return int(datetime.strptime(time_str, fmt).timestamp())
    except (ValueError, IndexError):
        return None


def parse_pbs_command(command_lines, spec):
    """
    Parses a PBS command line into parts.
    """
    if not command_lines:
        return []

    main_command = command_lines[-1]
    parts = shlex.split(main_command)

    if parts and parts[0] in ("mpiexec", "mpirun"):
        parts = parts[1:]

    if parts and parts[0] in ("singularity", "apptainer") and parts[1] == "exec":
        spec.container_image = parts[2]
        parts = parts[3:]

    return parts


class PBSTransformer(TransformerBase):
    """
    Transforms a JobSpec to/from a PBS (Portable Batch System) batch script.
    """

    def convert(self, spec):
        """
        Converts a JobSpec into a PBS submission script string.
        """
        script = PBSScript()

        script.add("N", spec.job_name or JobNamer().generate())
        script.add("A", spec.account)
        script.add("q", spec.queue)
        script.add("o", spec.output_file)
        script.add("e", spec.error_file)

        # Resource Selection (-l)
        select_parts = [f"select={spec.num_nodes}"]
        if spec.cpus_per_task > 1:
            select_parts.append(f"ncpus={spec.cpus_per_task}")
        if spec.gpus_per_task > 0:
            select_parts.append(f"ngpus={spec.gpus_per_task}")

        # PBS memory format often includes units like gb or mb
        if spec.mem_per_task:
            select_parts.append(f"mem={spec.mem_per_task.lower()}b")
        resource_str = ":".join(select_parts)

        wt = seconds_to_pbs(spec.wall_time)
        if wt:
            resource_str += f",walltime={wt}"
        script.add("l", resource_str)

        # Priority and scheduling
        pbs_prio = priority_to_pbs_priority(spec.priority)
        if pbs_prio != 0:
            script.add("p", pbs_prio)

        bt = epoch_to_pbs_begin_time(spec.begin_time)
        script.add("a", bt)

        # Environment & Execution
        if spec.environment:
            env_vars = ",".join([f"{k}='{v}'" for k, v in spec.environment.items()])
            script.add("v", env_vars)

        script.newline()

        # TODO: we probably want to keep this as a block of text, as it is.
        cmd_parts = ["mpiexec"]
        if spec.container_image:
            cmd_parts.extend(["singularity", "exec", spec.container_image])
        if spec.executable:
            cmd_parts.append(spec.executable)
        if spec.arguments:
            cmd_parts.extend(spec.arguments)

        script.add_line(" ".join(cmd_parts))
        script.newline()

        return script.render()

    def _parse(self, content, return_unhandled=False):
        """
        Parses a PBS submission script string into a JobSpec.
        """
        spec = JobSpec()
        pbs_re = re.compile(r"#PBS\s+-(\w)(?:\s+(.+))?")
        command_lines = []
        not_handled = set()

        resource_str, walltime_str = "", ""

        for line in content.splitlines():
            if not line.strip():
                continue

            m = pbs_re.match(line)
            if m:
                key, val = m.groups()
                if val:
                    val = val.split("#", 1)[0]

                val = val.strip() if val else ""
                if key == "N":
                    spec.job_name = val
                elif key == "A":
                    spec.account = val
                elif key == "q":
                    spec.queue = val
                elif key == "o":
                    spec.output_file = val
                elif key == "e":
                    spec.error_file = val
                elif key == "a":
                    spec.begin_time = pbs_begin_time_to_epoch(val)
                elif key == "p":
                    spec.priority = pbs_priority_to_priority(int(val))
                elif key == "l":
                    # The -l line can contain multiple comma-separated values
                    for part in val.split(","):
                        if "walltime" in part:
                            walltime_str = part.split("=", 1)[1]
                        # Don't join with 'select', it's separate
                        else:
                            resource_str += part
                else:
                    not_handled.add(key)
                continue

            if line.startswith("#"):
                continue
            command_lines.append(line)

        # Post-loop processing for complex -l string
        spec.wall_time = pbs_time_to_seconds(walltime_str)
        if resource_str:
            res_parts = resource_str.split(":")
            for part in res_parts:
                if not "=" in part:
                    continue
                k, v = part.split("=", 1)
                if k == "select":
                    spec.num_nodes = int(v)
                elif k == "ncpus":
                    spec.cpus_per_task = int(v)
                elif k == "ngpus":
                    spec.gpus_per_task = int(v)
                elif k == "mem":
                    spec.mem_per_task = v.upper().replace("B", "")

        # We again assume a block of text here.
        spec.script = command_lines
        if return_unhandled:
            return not_handled
        return spec
