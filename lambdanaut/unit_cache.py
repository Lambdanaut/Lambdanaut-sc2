from typing import List

import lib.sc2 as sc2

from collections import deque


class UnitCached(object):

    # Maximum length of self.last_positions deque list
    last_positions_maxlen = 10

    def __init__(self, unit: sc2.unit.Unit):
        self.snapshot = unit
        self.tag = unit.tag

        self.last_positions: List[sc2.position.Point2] = deque(maxlen=self.last_positions_maxlen)
        self.last_positions.append(unit.position)

    def update(self, unit):
        # Update last positions
        self.last_positions.append(unit.position)

        # Compare its health/shield since last step, to find out if it has taken any damage
        if unit.health_percentage < self.snapshot.health_percentage or \
                unit.shield_percentage < self.snapshot.shield_percentage:
            self.is_taking_damage = True
        else:
            self.is_taking_damage = False

        # Update snapshot
        self.snapshot = unit
        self.tag = unit.tag

    def __getattr__(self, item):
        """Passes calls down to the snapshot"""

        try:
            return self.__getattribute__(item)
        except AttributeError:
            return getattr(self.snapshot, item)