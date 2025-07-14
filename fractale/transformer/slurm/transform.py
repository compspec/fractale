#!/usr/bin/env python3

import re
import shlex
from datetime import datetime, timedelta

from fractale.logger.generate import JobNamer
from fractale.transformer.base import TransformerBase
from fractale.transformer.common import JobSpec


class SlurmScript:
    def __init__(self):
        self.script_lines = ["#!/bin/bash"]

    def newline(self):
        self.script_lines.append("")

    def add_line(self, line):
        """
        Add a custom line.
        """
        self.script_lines.append(line)

    def add(self, name, value=None):
        """
        Add a slurm (full) argument, --{key}={value}
        """
        # Empty arguments
        if not value:
            return
        self.script_lines.append(f"#SBATCH --{name}={value}")

    def render(self):
        return "\n".join(self.script_lines)

    def add_flag(self, name):
        """
        Add a slurm boolean flag (e.g., --exclusive)
        """
        self.script_lines.append(f"#SBATCH --{name}")


# Time conversions


def seconds_to_slurm_time(seconds):
    """
    Converts an integer number of seconds into a Slurm-compatible time string.
    Format: [days-]hours:minutes:seconds
    """
    # This shouldn't happen, but we return 0 so we use the default.
    if not seconds or seconds <= 0:
        return None

    # 86400 seconds in a day
    days, seconds_rem = divmod(seconds, 86400)
    hours, seconds_rem = divmod(seconds_rem, 3600)
    minutes, seconds = divmod(seconds_rem, 60)

    # Format the output
    if days > 0:
        # D-HH:MM:SS
        return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"

    # HH:MM:SS
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def epoch_to_slurm_begin_time(epoch_seconds: int) -> str:
    """
    Converts a Unix epoch timestamp (integer seconds) into a Slurm-compatible
    begin time string.
    Format: YYYY-MM-DDTHH:MM:SS
    """
    if not isinstance(epoch_seconds, int) or epoch_seconds < 0:
        raise ValueError("begin_time must be a positive integer (Unix epoch seconds).")

    return datetime.fromtimestamp(epoch_seconds).strftime("%Y-%m-%dT%H:%M:%S")


def slurm_time_to_seconds(self, time_str):
    if not time_str:
        return None
    days = 0

    # Allow this to error - we can catch after
    if "-" in time_str:
        day_part, time_str = time_str.split("-", 1)
        days = int(day_part)

    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = map(int, parts)
    elif len(parts) == 2:
        h, s = 0, 0
        m, s = map(int, parts)
    elif len(parts) == 1:
        h, s = 0, 0
        m = int(parts[0])
    return int(timedelta(days=days, hours=h, minutes=m, seconds=s).total_seconds())


def parse_slurm_command(command_lines, spec):
    """
    Pars a slurm command into parts.
    """
    # We use the last command line as the primary execution logic
    main_command = command_lines[-1]
    parts = shlex.split(main_command)

    # Unwrap common launchers
    if parts and parts[0] == "srun":
        parts = parts[1:]

    if parts and parts[0] in ("singularity", "apptainer") and parts[1] == "exec":
        spec.container_image = parts[2]
        # The rest is the command inside the container
        parts = parts[3:]

    # Handle input redirection
    if "<" in parts:
        try:
            idx = parts.index("<")
            spec.input_file = parts[idx + 1]
            # Remove '<' and the filename from the arguments
            parts.pop(idx)
            parts.pop(idx)
        except (ValueError, IndexError):
            pass
    return parts


def slurm_begin_time_to_epoch(self, time_str):
    """
    Converts a Slurm begin time string to Unix epoch seconds.
    """
    if not time_str:
        return None

    # Asking for now is akin to not setting (at least I think)
    if "now" in time_str.lower():
        return None

    # Attempt to parse the specific ISO-like format we generate.
    # Allow this to error.
    dt_object = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
    return int(dt_object.timestamp())


def priority_to_nice(priority):
    """
    Maps a semantic priority string ("high") to a Slurm nice value (-100).
    """
    # Higher nice value == LOWER priority
    mapping = {
        "low": 1000,
        "normal": 0,
        "high": -100,
        "urgent": -1000,
    }
    # Default to 'normal' (nice=0) if the string is None or not in the map
    return mapping.get(priority, 0)


def nice_to_priority(nice_value):
    """
    Maps a Slurm nice value (e.g., -100) back to a semantic string ("high").
    """
    if nice_value is None or nice_value == 0:
        return "normal"
    if nice_value > 0:
        return "low"

    # For negative values, we can create tiers
    if -1000 < nice_value < 0:
        return "high"

    # For nice_value <= -1000
    return "urgent"


class SlurmTransformer(TransformerBase):
    """
    A Slurm Transformer for converting a generic JobSpec into a Slurm batch script.

    This transformer maps the fields of the JobSpec to their corresponding #SBATCH
    directives and constructs a runnable script.
    """

    def convert(self, spec) -> str:
        """
        Convert a normalized jobspec to a Slurm batch script.

        Args:
            spec (JobSpec): The JobSpec object to convert.

        Returns:
            str: A string representing the Slurm batch script.
        """
        script = SlurmScript()

        # If we don't have a job name, generate one
        job_name = spec.job_name or JobNamer().generate()
        script.add("job-name", job_name)

        # Job Identity & Accounting
        script.add("account", spec.account)

        # I/O
        script.add("output", spec.output_file)
        script.add("error", spec.error_file)

        # Resource Requests
        script.add("nodes", spec.num_nodes)
        script.add("ntasks", spec.num_tasks)
        script.add("cpus-per-task", spec.cpus_per_task)

        # Slurm's --mem-per-cpu I think is how to specify memory per task
        if spec.mem_per_task:
            script.add("mem-per-cpu", spec.mem_per_task)
        if spec.gpus_per_task > 0:
            script.add("gpus-per-task", spec.gpus_per_task)

        # Scheduling and Constraints
        script.add("time", seconds_to_slurm_time(spec.wall_time))
        script.add("partition", spec.queue)

        # The 'nice' value in Slurm influences the job's priority.
        # A higher value means lower priority. This is an imperfect mapping.
        script.add("nice", spec.priority)

        if spec.exclusive_access:
            script.add_flag("exclusive")

        if spec.constraints:
            constraint_str = ",".join(spec.constraints)
            script.add("constraint", constraint_str)

        if spec.begin_time:
            script.add("begin", epoch_to_slurm_begin_time(spec.begin_time))
        script.add("chdir", spec.working_directory)

        # Dependencies
        if spec.depends_on:
            if isinstance(spec.depends_on, list):
                # Assuming a dependency type of 'afterok' as a default
                dependency_str = ":".join(spec.depends_on)
                script.add(f"dependency", f"afterok:{dependency_str}")
            else:
                script.append(f"dependency", spec.depends_on)

        # I am just adding this for readability
        script.newline()

        # Environment Variables
        if spec.environment:
            for key, value in spec.environment.items():
                script.add_line(f"export {key}='{value}'")
            script.newline()

        # Execution logic
        command_parts = []
        if spec.executable:
            command_parts.append(spec.executable)

        if spec.arguments:
            command_parts.extend(spec.arguments)

        # Handle containerization if an image is specified
        if spec.container_image:
            # Prepend with singularity/apptainer exec
            container_exec = ["singularity", "exec", spec.container_image]
            command_parts = container_exec + command_parts

        # Handle I/O redirection
        if spec.input_file:
            command_parts.append(f"< {spec.input_file}")

        script.add_line(" ".join(command_parts))
        script.newline()
        return script.render()

    def parse(self, script_content):
        """
        Parses the content of a Slurm batch script into a JobSpec object.

        Args:
            script_content (str): A string containing the Slurm script.

        Returns:
            JobSpec: A populated JobSpec object.
        """
        spec = JobSpec()

        # Heuristic: The last non-comment/non-export line is the main command.
        command_lines = []

        # Regex to capture #SBATCH directives
        sbatch_regex = re.compile(r"#SBATCH\s+(?:--| -)([\w-]+)(?:[=\s](.+))?")

        for line in script_content.splitlines():
            line = line.strip()
            if not line:
                continue

            # 1. Parse SBATCH directives
            match = sbatch_regex.match(line)
            if match:
                key, value = match.groups()
                value = value.strip() if value else None

                # Let this error for nice for now...
                if key == "nice":
                    spec.priority = nice_to_priority(int(value))

                # Map Slurm keys to JobSpec attributes
                elif key == "job-name":
                    spec.job_name = value
                elif key == "account":
                    spec.account = value
                elif key == "output":
                    spec.output_file = value
                elif key == "error":
                    spec.error_file = value
                elif key == "nodes":
                    spec.num_nodes = int(value)
                elif key == "ntasks":
                    spec.num_tasks = int(value)
                elif key == "cpus-per-task":
                    spec.cpus_per_task = int(value)
                elif key == "gpus-per-task":
                    spec.gpus_per_task = int(value)
                elif key == "mem-per-cpu":
                    spec.mem_per_task = value
                elif key == "partition":
                    spec.queue = value
                elif key == "exclusive":
                    spec.exclusive_access = True
                elif key == "chdir":
                    spec.working_directory = value
                elif key == "time":
                    spec.wall_time = slurm_time_to_seconds(value)
                elif key == "begin":
                    spec.begin_time = slurm_begin_time_to_epoch(value)
                elif key == "dependency":
                    # e.g., afterok:12345 or afterok:12345:67890
                    dep_parts = value.split(":")
                    spec.depends_on = dep_parts[-1] if len(dep_parts) == 2 else dep_parts[1:]
                continue

            # 2. Skip other comments
            if line.startswith("#"):
                continue

            # 3. Parse environment variables
            if line.lower().startswith("export "):
                env_match = re.match(r"export\s+([^=]+)=(.*)", line)
                if env_match:
                    env_key, env_val = env_match.groups()
                    # Strip quotes from value
                    spec.environment[env_key] = env_val.strip("'\"")
                continue

            # 4. Assume any other non-empty line is part of the command
            command_lines.append(line)

        # 5. Deconstruct the main command line
        if command_lines:
            parts = self.parse_slurm_command(command_lines, spec)
            if parts:
                spec.executable = parts[0]
                spec.arguments = parts[1:]

        return spec
