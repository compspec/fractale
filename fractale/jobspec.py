import copy
from contextlib import contextmanager

import fractale.utils as utils


def flatten_jobspec_resources(jobspec):
    """
    Given a jobspec, turn the required resources into a flattened version.

    This is intended for subsystem matching that doesn't assume any structure.
    E.g., the database solved backend, which was first just for prototyping.
    """
    resources = {}
    resource_list = copy.deepcopy(jobspec["resources"])
    multiplier = 1

    # Resource lists are nested, under "with"
    while resource_list:
        requires = resource_list.pop(0)
        resource_type = requires["type"]
        resource_count = requires.get("count")

        # The slot is a marker for the set we care about matching
        if resource_type == "slot":
            multiplier = resource_count or 1
        else:
            if resource_type not in resources:
                resources[resource_type] = 0
            resources[resource_type] += resource_count * multiplier
        resource_list += requires.get("with") or []
    return resources


def extract_slot(jobspec):
    """
    Given a jobspec, parse into slot and return counts and requirements.
    This is intended for the containment subsystem.
    """
    js = utils.load_jobspec(jobspec)
    slots = []

    # Tasks will have per slot (this is a list of one item, required)
    # In the future Flux could theoretically support more than one task
    # (and slot) in which case we would need to select the label
    task = js["tasks"][0]
    slot_name = task["slot"]

    # I'm not sure I've ever seen anything other than "per_slot"
    # Might as well raise an error and alert if that happens :)
    slot_count = task.get("count", {})
    if "per_slot" not in slot_count:
        raise ValueError(f"Unexpected value for tasks->slot->count: {slot_count}")

    # Assume a default of one per slot
    slot_count = slot_count.get("per_slot") or 1

    def check_resource(resource, is_slot=False):
        """
        Recursive function to dig into resources under "with.
        Once we find the slot, we save the entire thing (with nesting)
        as a Slot class, which better exposes the counts, etc.
        """
        if "with" in resource:
            for item in resource["with"]:
                if is_slot:
                    new_slot = copy.deepcopy(item)
                    total = item["count"] * slot_count
                    slots.append(Slot(new_slot, total=total))

                # Again, we can eventually support multiple slots by
                # checking the label. Flux right now only expects one.
                check_resource(item, item["type"] == "slot")

    # Kick it off, y'all
    for resource in js["resources"]:
        check_resource(resource, resource["type"] == "slot")
    return slots


class Slot:
    """
    A slot is like a wedge we stick in the containment graph, and say
    "We are defining our needs for the resources below this wedge, and we need
    this many of this wedge." Since we need to evaluate the resource counts
    dynamically, we provide a context-based function to do that. It will restore
    back to the original state when the context is left. The expected usage is:

    # Temporary view of the slot to evaluate with (make changes to)
    with slot.evaluate() as evaluator:
        # This is the current spot we are at in the slot
        requires = evaluator.next_requirement()
        v_type, count = next(requires)

    Check for a StopIteration exception to know when we are done.
    """

    def __init__(self, spec, total=1):
        # This is a nested structure, e.g.,
        # {'type': 'socket', 'count': 1, 'with': [{'type': 'core', 'count': 4}]}
        self.spec = spec
        self.total = total
        # This holds state for what we find during an evaluation
        self._found = {}

    @property
    def start_type(self):
        """
        The start type identifies the top of the slot
        """
        return self.spec["type"]

    @contextmanager
    def evaluate(self):
        """
        Yield a temporary copy of the spec in case it is mutated.
        Also init and reset found, so we can evaluate multiple spots
        for satisfying the same slot instance.
        """
        spec = copy.deepcopy(self.spec)
        self._found = {}
        try:
            yield self
        # Restore the original state, you mangy animal
        finally:
            self.spec = spec
            self._found = {}

    def next_requirement(self):
        """
        Yield requirements. We are strict for now, requiring that we see all levels.
        """
        resources = [copy.deepcopy(self.spec)]
        while resources:
            resource = resources.pop(0)
            yield resource["type"], resource.get("count") or 1
            if "with" in resource:
                resources += resource["with"]

    def count(self, v_type):
        """
        Get the count for a resource type that has been found.
        """
        return self._found.get(v_type) or 0

    def found(self, v_type, count=1, needed=None):
        """
        Indicate that a type was found.
        """
        if v_type not in self._found:
            self._found[v_type] = 0
        self._found[v_type] += 1

        # This tells the caller if we are done with the type.
        if needed is not None and self._found[v_type] == needed:
            return True
        return False

    def satisfied(self):
        """
        Determine if the slot is satisifed, meaning all needed counts
        are <= 0. This should be run in the context of evaluate.
        """
        # These are all the requirements
        needed = {}
        for requires_type, requires_count in self.next_requirement():
            needed[requires_type] = requires_count

        updated = copy.deepcopy(needed)
        for found_type, found_count in self._found.items():
            if found_count >= needed[found_type]:
                del updated[found_type]

        # If updated is empty, we got all needed
        return not updated
