import re
import shlex
from datetime import datetime, timedelta

from fractale.transformer.base import Script, TransformerBase
from fractale.transformer.common import JobSpec


class LSFScript(Script):
    """
    A helper class to build an LSF (#BSUB) batch script line by line.
    """

    def __init__(self):
        self.script_lines = ["#!/bin/bash"]
        self.directive = "#BSUB"


def priority_to_lsf_priority(priority_str):
    """
    Maps a semantic string to an LSF priority value (1-65535).
    """
    return {
        "low": 10,
        "normal": 50,
        "high": 100,
        "urgent": 200,
    }.get(priority_str, 50)


def lsf_priority_to_priority(lsf_priority):
    """
    Maps an LSF priority value back to a semantic string.
    """
    if lsf_priority is None:
        return "normal"
    if lsf_priority <= 10:
        return "low"
    if lsf_priority <= 50:
        return "normal"
    if lsf_priority <= 100:
        return "high"
    return "urgent"


def seconds_to_lsf_walltime(total_seconds):
    """
    Converts integer seconds to LSF HH:MM walltime format.
    """
    if not isinstance(total_seconds, int) or total_seconds <= 0:
        return None
    # LSF's -W flag expects minutes or HH:MM
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}"


def lsf_walltime_to_seconds(time_str):
    """
    Converts LSF HH:MM walltime string back to integer seconds.
    """
    if not time_str:
        return None
    try:
        h, m = map(int, time_str.split(":"))
        return int(timedelta(hours=h, minutes=m).total_seconds())
    except (ValueError, IndexError):
        return None


def epoch_to_lsf_begin_time(epoch_seconds):
    """
    Converts Unix epoch to LSF's begin time format for the '-b' flag.
    """
    if not isinstance(epoch_seconds, int) or epoch_seconds <= 0:
        return None
    return datetime.fromtimestamp(epoch_seconds).strftime("%Y:%m:%d:%H:%M")


def lsf_begin_time_to_epoch(time_str):
    """
    Converts an LSF begin time string back to Unix epoch.
    """
    if not time_str:
        return None
    try:
        return int(datetime.strptime(time_str, "%Y:%m:%d:%H:%M").timestamp())
    except (ValueError, IndexError):
        return None


def parse_lsf_command(command_lines, spec):
    """
    Parses an LSF command line into parts.
    """
    if not command_lines:
        return []

    main_command = command_lines[-1]
    parts = shlex.split(main_command)

    # Common LSF launchers include jsrun (Spectrum MPI) or mpirun
    if parts and parts[0] in ("jsrun", "mpirun"):
        parts = parts[1:]

    if parts and parts[0] in ("singularity", "apptainer") and parts[1] == "exec":
        spec.container_image = parts[2]
        parts = parts[3:]

    return parts


# --- Main Transformer Class ---


class LSFTransformer(TransformerBase):
    """
    Transforms a JobSpec to/from an LSF (#BSUB) batch script.
    """

    def convert(self, spec):
        """
        Converts a JobSpec into an LSF submission script string.
        """
        script = LSFScript()

        script.add("J", spec.job_name or JobNamer().generate())
        script.add("P", spec.account)
        script.add("q", spec.queue)
        script.add("o", spec.output_file)
        script.add("e", spec.error_file)

        # --- Resource Specification ---
        # LSF is typically task-centric with the -n flag
        script.add("n", spec.num_tasks * spec.num_nodes)

        wt = seconds_to_lsf_walltime(spec.wall_time)
        script.add("W", wt)

        # Build the complex -R "rusage[...]" string
        rusage_parts = []
        if spec.mem_per_task:
            # LSF typically expects memory in MB
            mem_mb = int(re.sub(r"[^0-9]", "", spec.mem_per_task))
            if "G" in spec.mem_per_task.upper():
                mem_mb *= 1024
            rusage_parts.append(f"mem={mem_mb}")

        if spec.gpus_per_task > 0:
            rusage_parts.append(f"ngpus_excl_p={spec.gpus_per_task}")

        if rusage_parts:
            script.add("R", f'"rusage[{":".join(rusage_parts)}]"')

        if spec.exclusive_access:
            script.add("x", "")  # LSF uses -x for exclusive node access

        # --- Priority and Scheduling ---
        lsf_prio = priority_to_lsf_priority(spec.priority)
        if lsf_prio != 50:  # Don't add if it's the default
            script.add("sp", lsf_prio)

        bt = epoch_to_lsf_begin_time(spec.begin_time)
        script.add("b", bt)

        script.newline()

        # --- Environment & Execution ---
        if spec.environment:
            for key, value in spec.environment.items():
                script.add_line(f"export {key}='{value}'")
            script.newline()

        cmd_parts = ["jsrun"]  # A common launcher in LSF environments
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
        Parses an LSF submission script string into a JobSpec.
        """
        spec = JobSpec()
        bsub_re = re.compile(r"#BSUB\s+-(\w)(?:\s+(.+))?")
        command_lines = []
        not_handled = set()

        for line in content.splitlines():
            if not line.strip():
                continue

            m = bsub_re.match(line)
            if m:
                key, val = m.groups()
                if val:
                    val = val.split("#", 1)[0]

                val = val.strip() if val else ""
                if key == "J":
                    spec.job_name = val
                elif key == "P":
                    spec.account = val
                elif key == "q":
                    spec.queue = val
                elif key == "o":
                    spec.output_file = val
                elif key == "e":
                    spec.error_file = val
                elif key == "b":
                    spec.begin_time = lsf_begin_time_to_epoch(val)
                elif key == "sp":
                    spec.priority = lsf_priority_to_priority(int(val))
                elif key == "n":
                    spec.num_tasks = int(val)
                elif key == "W":
                    spec.wall_time = lsf_walltime_to_seconds(val)
                elif key == "x":
                    spec.exclusive_access = True
                elif key == "R":
                    # Parse rusage string like "rusage[mem=4096:ngpus_excl_p=1]"
                    rusage_match = re.search(r"rusage\[(.*)\]", val)
                    if rusage_match:
                        for part in rusage_match.group(1).split(":"):
                            k, v = part.split("=", 1)
                            if k == "mem":
                                spec.mem_per_task = f"{v}M"  # Assume parsed value is MB
                            elif k == "ngpus_excl_p":
                                spec.gpus_per_task = int(v)
                else:
                    not_handled.add(key)
                continue

            if line.startswith("#"):
                continue
            command_lines.append(line)

        # In LSF, -n usually defines total tasks. If num_nodes is not specified
        # we can assume 1, but this is an imperfect mapping back.
        if spec.num_tasks and spec.num_nodes == 1:
            pass

        # We again assume a block of text here.
        spec.script = command_lines
        if return_unhandled:
            return not_handled
        return spec
