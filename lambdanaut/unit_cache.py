from collections import deque
from typing import List, Union

import lib.sc2 as sc2
import lib.sc2.constants as const
from lib.sc2.game_state import EffectData
from lib.sc2.position import Point2
from lib.sc2.unit import Unit


class UnitCached(object):

    # Maximum length of self.last_positions deque list
    last_positions_maxlen = 10

    def __init__(self, bot, unit: sc2.unit.Unit):
        self.bot = bot

        self.snapshot: Unit = unit
        self.tag: int = unit.tag

        self.is_taking_damage = False

        # Game loop last seen
        self.last_seen: float = 0

        # The last game loop we performed a priority retarget for this unit
        self.last_priority_retarget: int = 0

        self.last_positions: List[sc2.position.Point2] = deque(maxlen=self.last_positions_maxlen)
        self.last_positions.append(unit.position)

        # If we're currently avoiding an effect(like a bile)
        self.avoiding_effect: Point2 = None

    def update(self, unit: Unit):
        # Update last positions
        self.last_positions.append(unit.position)

        # Update last time we saw this unit
        self.last_seen = self.bot.state.game_loop

        # Compare its health/shield since last step, to find out if it has taken any damage
        if unit.health_percentage < self.snapshot.health_percentage or \
                unit.shield_percentage < self.snapshot.shield_percentage:
            self.is_taking_damage = True
        else:
            self.is_taking_damage = False

        # Update the position of any effects we should be avoiding
        self.avoiding_effect = self.get_avoiding_effect_position(unit, self.bot.state.effects)

        # Update snapshot
        self.snapshot = unit
        self.tag = unit.tag

    def get_avoiding_effect_position(self, unit: Unit, effects: List[EffectData]) -> Union[None, Point2]:
        """
        Determines if we should be avoiding an effect.
        Returns the effects position if so, otherwise returns None
        """

        if unit.is_mine:
            effects_to_avoid = {
                const.EffectId.RAVAGERCORROSIVEBILECP,
                const.EffectId.BLINDINGCLOUDCP,
                const.EffectId.PSISTORMPERSISTENT,
                # const.EffectId.LURKERMP,
            }

            for effect in filter(lambda e: e.id in effects_to_avoid, effects):
                for position in effect.positions:
                    if unit.distance_to(position) < 4 + unit.radius:
                        return position

        return None

    def can_priority_retarget(self, game_loop):
        """
        The unit can priority retarget if the last priority retarget time was over X frames ago

        Called from manager.micro.Micro.manage_priority_targeting()
        """
        return game_loop - self.last_priority_retarget > 12  # About half a second

    def __getattr__(self, item):
        """Passes calls down to the snapshot"""
        try:
            return self.__getattribute__(item)
        except AttributeError:
            return getattr(self.snapshot, item)

    def __getitem__(self, item):
        """Passes calls down to the snapshot"""
        return self.snapshot.position_tuple[item]
