import json
from dataclasses import dataclass


@dataclass
class Match:
    """
    A single match is a datum that goes into a match set.
    """

    cluster: str
    subsystem: str
    requires: dict
    details: dict


class MatchSet:
    """
    A MatchSet includes one or more matches of clusters-> subsystems to a spec
    """

    def __init__(self):
        # Lookup by cluster, subsystem, and then requirements and matches.
        # This needs to be enough to return to the called and generate
        # templates to submit jobs.
        self.matches = {}

    @property
    def count(self):
        """
        Return the number of cluster matches.
        """
        return len(self.matches.keys())

    @property
    def clusters(self):
        """
        Return a list of clusters.
        """
        return list(self.matches)

    def all(self):
        """
        Custom function to iterate over matches
        """
        return list(self.iterset())

    def remove(self, cluster):
        """
        Remove a cluster from a match.
        """
        if cluster in self.matches:
            del self.matches[cluster]

    def iterset(self):
        """
        Custom function to iterate over matches
        """
        for cluster, by_subsystem in self.matches.items():
            for subsystem, matches in by_subsystem.items():
                for match in matches:
                    yield match

    def add(self, cluster, subsystem, requires, details):
        """
        Add a match, including cluster, subsystem, requirements, and details.
        """
        new_match = Match(cluster, subsystem, requires, details)
        if cluster not in self.matches:
            self.matches[cluster] = {}
        if subsystem not in self.matches[cluster]:
            self.matches[cluster][subsystem] = []
        # this could be given directly, but I don't want to assume
        # that a cluster and subsystem only has one possible match.
        self.matches[cluster][subsystem].append(new_match)
