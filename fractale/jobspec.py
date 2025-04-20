import copy


def flatten_jobspec_resources(jobspec):
    """
    Given a jobspec, turn the required resources into a flattened version.
    """
    resources = {}
    resource_list = copy.deepcopy(jobspec["resources"])
    multiplier = 1
    while resource_list:
        requires = resource_list.pop(0)
        resource_type = requires["type"]
        resource_count = requires.get("count")
        if resource_type == "slot":
            multiplier = resource_count or 1
        else:
            if resource_type not in resources:
                resources[resource_type] = 0
            resources[resource_type] += resource_count * multiplier
        resource_list += requires.get("with") or []
    return resources
