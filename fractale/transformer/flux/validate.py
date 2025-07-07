import re
from io import StringIO

from flux.cli.batch import BatchCmd
from flux.job.directives import DirectiveParser

import fractale.utils as utils
from fractale.transformer.common import JobSpec


class Validator(BatchCmd):
    """
    The validator validates a Flux batch script, and also
    parses arguments into the standard format.
    """

    def derive_failure_reason(self, message):
        """
        Why did the directive parsing fail?
        """
        line = None
        if "line" in message:
            line = int(message.split("line", 1)[-1].split(":", 1)[0])

        # E.g., # # Flux
        if "sentinel changed" in message:
            return "sentinel changed", line

        # Directive after top of script
        if "orphan 'flux:'" in message.lower():
            return "orphan flux", line

        if "unknown directive" in message.lower():
            return "unknown directive", line

        # Always investigate edge cases!
        print("Unseen issue with parsing directive, investigate:")
        print(message)
        import IPython

        IPython.embed()

    def get_directive_parser(self, content, changes=None):
        """
        Read batch script into string, and get directive parser

        If failure is due to a line that can be removed, do it.
        """
        if changes is None:
            changes = []
        string_io = StringIO(content)
        try:
            batchscript = DirectiveParser(string_io)
        except Exception as e:
            string_io.close()
            reason, line = self.derive_failure_reason(" ".join(e.args))
            if line is not None:
                lines = content.split("\n")
                deleted_line = lines[line - 1]
                changes.append({"line": deleted_line, "reason": reason})
                del lines[line - 1]
                return self.get_directive_parser("\n".join(lines), changes)
            else:
                print("The error message did not return a line, take a look why.")
                import IPython

                IPython.embed()
        string_io.close()
        return batchscript, changes

    def parse(self, filename):
        """
        Validate and parse, yielding back arguments.
        """
        content = utils.read_file(filename)

        # Changes are removed lines to get it to read
        batchscript, changes = self.get_directive_parser(content)
        if changes:
            changes = "\n".join(changes)
            raise ValueError(f"Jobspec is invalid, required changes: {changes}")

        # Assume the script is not hashbang, command or directive
        script = [x for x in batchscript.script.split("\n") if not x.startswith("#") and x.strip()]

        # We will populate the common JobSpec
        js = JobSpec(arguments=script)

        # Not parsed yet in flux:
        #   1. input_file (Not sure what this is)
        #   2. I don't think flux has memory per slot
        #   3. I know flux has constraints, add parsed here
        for item in batchscript.directives:
            try:
                # Validation, then mapping to standard
                if item.action == "SETARGS":
                    # This should only be one value, but don't assume
                    for key, value in self.parse_argument_delta(item.args):
                        js = self.update_jobspec(js, key, value)

            except Exception:
                name = " ".join(item.args)
                raise ValueError(f"validation failed at {name} line {item.lineno}")
        return js

    def update_jobspec(self, js, key, value):
        """
        Direct mapping of a key from parsed Flux command line into standard
        """
        if key == "nodes":
            js.num_nodes = value

        # These need additional parsing, and can allow customization
        elif key == "setattr":
            for v in value:
                key, v = v.split("=", 1)
                if key == "container_image":
                    js.container_image = v
                else:
                    js.attrs[key] = v
        elif key == "setopt":
            for v in value:
                key, v = v.split("=", 1)
                js.options[key] = v

        elif key == "cwd":
            js.working_directory = value
        elif key == "nslots":
            js.num_tasks = value
        elif key == "cores_per_task":
            js.cores_per_task = value
        elif key == "gpus_per_task":
            js.gpus_per_slot = value
        elif key == "priority":
            js.priority = value
        elif key == "executable":
            js.executable = value
        elif key == "arguments":
            js.arguments += value
        elif key == "output":
            js.output_file = value
        elif key == "error":
            js.error_file = value
        elif key == "exclusive":
            js.exclusive_access = value
        elif key == "job_name":
            js.job_name = value
        elif key == "env":
            js.env = value
        elif key == "queue":
            js.queue = value
        elif key == "time_limit":
            js.wall_time = parse_time_to_seconds(value)
        elif key == "bank":
            js.account = value
        elif key == "dependency":
            if not js.depends_on:
                js.depends_on = []
            js.depends_on += value
        else:
            print(f"Warning: not handled: {key}={value}")
        return js

    def parse_argument_delta(self, args):
        """
        Get a single parsed arg by looking at the parser delta.
        """
        defaults = self.parser.parse_args([])
        updated = self.parser.parse_args(args)

        # Find what's different - this will only be one value
        for key, value in vars(updated).items():
            if value != getattr(defaults, key):
                yield key, value


def parse_time_to_seconds(time_str):
    """
    Parses a time string like "1h30m", "1d", "50m", "3600s" into seconds.
    """
    if not time_str:
        return None

    total_seconds = 0
    # Regex to find numbers and their units (d, h, m, s)
    pattern = re.compile(r"(\d+)([dhms])")
    matches = pattern.findall(time_str.lower())

    if not matches and time_str.isdigit():
        return int(time_str)

    for value, unit in matches:
        value = int(value)
        if unit == "d":
            total_seconds += value * 86400
        elif unit == "h":
            total_seconds += value * 3600
        elif unit == "m":
            total_seconds += value * 60
        elif unit == "s":
            total_seconds += value

    return total_seconds if total_seconds > 0 else None


def map_numeric_priority_to_class_name(priority):
    """
    Maps a numerical priority value to a pre-defined Kubernetes PriorityClass name.
    Flux has a default priority of 16. I haven't looked at others yet.
    """
    if priority is None:
        return "normal"

    if priority <= 15:
        return "low"
    elif priority == 16:
        return "normal"
    elif 17 <= priority <= 99:
        return "high"
    else:
        return "urgent"
