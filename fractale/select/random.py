import random


class RandomSelection:
    """
    Random selection selects randomly from a list of contenders.
    """

    def select(self, _, clusters):
        return random.choice(clusters)
