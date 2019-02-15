from collections import Counter, defaultdict
from itertools import takewhile
import math
import random
from typing import Any, Dict, List, Optional, Tuple, Union

import sc2
import sc2.constants as const
from sc2.position import Point2, Point3

import lambdanaut.builds as builds
import lambdanaut.const2 as const2
import lambdanaut.clustering as clustering
import lambdanaut.unit_cache as unit_cache
import lambdanaut.utils as utils

from lambdanaut.const2 import \
    (Messages, BuildManagerCommands, ForceManagerCommands, ResourceManagerCommands,
     ForcesStates, OverlordStates)
from lambdanaut.builds import Builds, BuildStages, BUILD_MAPPING, DEFAULT_NEXT_BUILDS
from lambdanaut.expiringlist import ExpiringList


VERSION = '2.6'
DEBUG = True
BUILD = Builds.EARLY_GAME_DEFAULT_OPENER


class IntelManager(Manager):
    """
    Class for reading incoming pubsub messages and making adjustments to the intel
    held in the bot class.

    This is the only class with permission to directly access and edit variables in
    the Lambdanaut class and other managers.
    """

    name = 'Intel Manager'

    def __init__(self, bot):
        super(IntelManager, self).__init__(bot)

        self.has_scouted_enemy_air_tech = False
        self.has_scouted_enemy_counter_with_roaches = False
        self.has_scouted_enemy_counter_midgame_broodlord_rush = False
        self.has_scouted_enemy_greater_force = ExpiringList()  # Will contain True or nothing

        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
        self.subscribe(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE)
        self.subscribe(Messages.ARMY_FOUND_ENEMY_BASE)

    async def read_messages(self):
        for message, val in self.messages.items():

            # Enemy location not where it was expected
            lost_enemy_location_msgs = {
                Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION,
                Messages.ARMY_COULDNT_FIND_ENEMY_BASE}
            if message in lost_enemy_location_msgs:
                self.ack(message)

                # Mark the current enemy start location as invalid
                self.bot.not_enemy_start_locations.add(self.bot.enemy_start_location)

                # Get potential enemy start locations that we have not already tried
                enemy_start_locations = \
                    [loc for loc in
                     self.bot.enemy_start_locations if loc not in
                     self.bot.not_enemy_start_locations]

                try:
                    new_enemy_start_location = enemy_start_locations[0]
                except IndexError:
                    # This would indicate a bug where we were unable to find the enemy in any start location
                    self.print("Couldn't find enemy base in any start location")
                    continue

                self.bot.enemy_start_location = new_enemy_start_location

            # Found enemy location
            found_enemy_location_msgs = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE,
                Messages.ARMY_FOUND_ENEMY_BASE}
            if message in found_enemy_location_msgs:
                self.ack(message)

                point = val
                enemy_start_locations = [loc for loc in self.bot.enemy_start_locations
                                         if loc != self.bot.start_location]
                new_enemy_start_location = point.closest(enemy_start_locations)

                self.bot.enemy_start_location = new_enemy_start_location

    def enemy_counter_with_midgame_broodlord_rush(self):
        """Checks the map to see if there are any visible units we should counter with a broodlord rush"""
        if not self.has_scouted_enemy_counter_midgame_broodlord_rush:

            factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            tank_count = len(self.bot.known_enemy_units.of_type(
                {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if factory_count > 2 or tank_count > 3:
                self.has_scouted_enemy_counter_midgame_broodlord_rush = True
                return True

        return False

    def enemy_counter_with_midgame_roach_spotted(self):
        """Checks the map to see if there are any visible units we should counter with roach/hydra"""
        if not self.has_scouted_enemy_counter_with_roaches:
            enemy_counter_with_roach_types = {
                const.ROACH, const.ROACHWARREN, const.HELLIONTANK, const.PLANETARYFORTRESS}

            enemy_counter_with_roach_units = self.bot.known_enemy_units.of_type(enemy_counter_with_roach_types)

            factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            # reaper_count = len(self.bot.known_enemy_units.of_type(const.REAPER))
            tank_count = len(self.bot.known_enemy_units.of_type(
                {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if enemy_counter_with_roach_units.exists \
                    or factory_count > 1 \
                    or tank_count > 1:
                self.has_scouted_enemy_counter_with_roaches = True
                return True

        return False

    def enemy_air_tech_scouted(self):
        """Checks the map to see if there are any visible enemy air tech"""
        if not self.has_scouted_enemy_air_tech:
            enemy_air_tech_types = {
                const.STARGATE, const.SPIRE, const.LIBERATOR, const.BATTLECRUISER, const.ORACLE,
                const.BANSHEE, const.SMBANSHEE, const.SMARMORYBANSHEE,
                const.PHOENIX, const.BROODLORD, const.DARKSHRINE, const.GHOSTACADEMY,
                const.GHOST, const.MUTALISK, const.LURKERDENMP, const.LURKERMP, const.ROACHBURROWED,
                const.STARPORTTECHLAB, const.DARKTEMPLAR, const.LURKER, const.LURKERDEN}

            enemy_air_tech_units = self.bot.known_enemy_units.of_type(enemy_air_tech_types)

            if enemy_air_tech_units.exists:
                self.has_scouted_enemy_air_tech = True
                return True

        return False

    def greater_enemy_force_scouted(self):
        if not self.has_scouted_enemy_greater_force.contains(
                True, self.bot.state.game_loop):
            units = self.bot.units(const2.ARMY_UNITS)
            enemy_units = self.bot.known_enemy_units

            units_strength = 0
            for unit in units:
                units_strength += self.bot.strength_of(unit)
            enemy_strength = 0
            for unit in enemy_units:
                enemy_strength += self.bot.strength_of(unit)

            if enemy_strength > units_strength * 0.3:
                self.has_scouted_enemy_greater_force.add(
                    True, self.bot.state.game_loop, expiry=30)
                return True

            return False

    def enemy_moving_out_scouted(self):
        """
        Checks to see if enemy units are moving out towards us
        """
        enemy_units = self.bot.known_enemy_units
        exclude_nonarmy_types = const2.WORKERS | {const.OVERLORD, const.OVERSEER}
        enemy_units = enemy_units.exclude_type(exclude_nonarmy_types).not_structure.\
            closer_than(80, self.bot.enemy_start_location)

        closer_enemy_counts = 0
        if len(enemy_units) > 3:
            for enemy_unit in enemy_units:
                if self.bot.moving_closer_to(
                        unit=enemy_unit,
                        cache=self.bot.enemy_cache,
                        point=self.bot.start_location):
                    closer_enemy_counts += 1

            # At least 6 enemy units were spotted moving closer to us for 10 iterations
            # Also the force manager is not currently attacking or moving to attack
            if self.bot.force_manager.state not in {ForcesStates.ATTACKING, ForcesStates.MOVING_TO_ATTACK} and \
                    closer_enemy_counts > 5:
                return True

        return False

    async def assess_game(self):
        """
        Assess the game's state and send out applicable messages
        """

        if self.enemy_air_tech_scouted():
            self.publish(Messages.ENEMY_AIR_TECH_SCOUTED)
        if self.enemy_counter_with_midgame_roach_spotted():
            self.publish(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)
        if self.enemy_counter_with_midgame_broodlord_rush():
            self.publish(Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD)
        if self.greater_enemy_force_scouted():
            self.publish(Messages.FOUND_ENEMY_GREATER_FORCE)
            if len(self.bot.townhalls.ready) < 3:
                self.publish(Messages.FOUND_ENEMY_EARLY_AGGRESSION)
        if self.enemy_moving_out_scouted():
            self.publish(Messages.ENEMY_MOVING_OUT_SCOUTED)

    async def run(self):
        await self.read_messages()
        await self.assess_game()


class BuildManager(Manager):

    name = 'Build Manager'

    def __init__(self, bot, starting_build):
        super(BuildManager, self).__init__(bot)

        assert isinstance(starting_build, Builds)

        self.starting_build = starting_build

        self.builds = [
            None,  # Opener
            None,  # Early-game
            None,  # Mid-game
            None,  # Late-game
        ]
        self.build_stage = builds.get_build_stage(starting_build)

        self.build_target = None
        self.last_build_target = None

        # Flag for if we've already changed the midgame. We only want to do this once
        self.has_switched_midgame = False

        # Flags to decide whether we should disregard worker and townhall build targets
        self.stop_worker_production = False
        self.stop_townhall_production = False

        # If True is in this list, it's equivalent to having stop_worker_production
        # and stop_townhall_production set
        self._stop_nonarmy_production = ExpiringList()

        # Message subscriptions
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN)
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH)
        self.subscribe(Messages.ENEMY_MOVING_OUT_SCOUTED)
        self.subscribe(Messages.FOUND_ENEMY_EARLY_AGGRESSION)
        self.subscribe(Messages.ENEMY_AIR_TECH_SCOUTED)
        self.subscribe(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)
        self.subscribe(Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD)
        self.subscribe(Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES)
        self.subscribe(Messages.STATE_EXITED)

        # Expansion index used for trying other expansions if the one we're trying is blocked
        self.next_expansion_index = 0

        # Recent commands issued. Uses constants defined in const2.py
        self._recent_commands = ExpiringList()

        # Set of the ids of the special build targets that are currently active
        self.active_special_build_target_ids = set()

        # Constant mapping of unit_type to its creation ability for fast access
        # (like the creation ability for spawning a drone)
        self.unit_type_to_creation_ability_map = {
            unit_id: unit.creation_ability for unit_id, unit in self.bot._game_data.units.items()}

    async def init(self):
        self.determine_opening_build()
        self.add_build(self.starting_build)

    def can_afford(self, unit):
        """Returns boolean indicating if the player has enough minerals,
        vespene, and supply to build the unit"""

        can_afford = self.bot.can_afford(unit)
        return \
            can_afford.can_afford_minerals and \
            can_afford.can_afford_vespene and \
            can_afford.have_enough_supply

    def determine_opening_build(self):
        # Chance of cheese on smaller maps (2 player start locations)
        if len(self.bot.enemy_start_locations) < 3:
            # Randomly do ravager all-ins against terran and protoss
            if self.bot.enemy_race in {sc2.Race.Terran, sc2.Race.Protoss}:
                if not random.randint(0, 7):
                    self.starting_build = Builds.RAVAGER_ALL_IN

    def add_build(self, build):
        self.print("Adding build order: {}".format(build.name))

        assert isinstance(build, Builds)

        build_stage = builds.get_build_stage(build)

        # If we're switching the midgame that has already been set, set a flag
        if build_stage == BuildStages.MID_GAME and \
                self.builds[BuildStages.MID_GAME.value] != None:
            self.has_switched_midgame = True

        # Publish a message about the newly added build
        self.publish(Messages.NEW_BUILD, build)

        self.builds[build_stage.value] = build

    def add_next_default_build(self):
        latest_build = self.get_latest_build()

        next_default_build = DEFAULT_NEXT_BUILDS[latest_build]
        if next_default_build is not None:
            self.add_build(next_default_build)

    def get_latest_build(self) -> builds.Builds:
        """Returns the latest build order added"""
        return list(takewhile(lambda build: build is not None, self.builds))[-1]

    def get_current_build_queue(self):
        """Returns the current build queue"""

        build_queue = []
        for build in self.builds:
            if build is None:
                break
            build_targets = BUILD_MAPPING[build]
            build_queue += build_targets

        return build_queue

    async def read_messages(self):
        """
        Reads incoming subscribed messages and updates the build order based
        on them.
        """

        for message, val in self.messages.items():

            # Messages indicating that it's safe to expand early
            safe_to_expand_early = {Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN}
            if message in safe_to_expand_early:
                self.ack(message)

            # Messages indicating to take a cautious early game
            cautious_early_game = {Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN}
            if message in cautious_early_game:
                self.ack(message)
                # If we're already defending hard, don't start defending soft
                if Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE not in self.builds:
                    self.add_build(Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS)

            # Messages indicating we need to defend a rush
            defensive_early_game = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY,
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH,
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH}
            if message in defensive_early_game:
                self.ack(message)

                # Cancel constructing hatcheries that are not near completion
                constructing_hatcheries = self.bot.units(const.HATCHERY).not_ready
                if constructing_hatcheries.exists:
                    self.print("Cancelling all constructing hatcheries")
                    for hatchery in constructing_hatcheries:
                        enemy_units = self.bot.known_enemy_units
                        if enemy_units.exists:
                            nearby_enemy_units = enemy_units.closer_than(18, hatchery)
                            if nearby_enemy_units or hatchery.build_progress < 0.8:
                                self.bot.actions.append(hatchery(const.CANCEL))

                # Switch to a defensive build
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)

            # Messages indicating we need to defend an early aggression
            early_aggression = {Messages.FOUND_ENEMY_EARLY_AGGRESSION}
            if message in early_aggression:
                self.ack(message)

                # Switch to a defensive build
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)

            # Messages indicating we need to build spore crawlers
            spore_crawlers_early_game = {Messages.ENEMY_AIR_TECH_SCOUTED}
            if message in spore_crawlers_early_game:
                self.ack(message)
                self.add_build(Builds.EARLY_GAME_SPORE_CRAWLERS)

            # Messages indicating roach_hydra mid game is ideal
            roach_hydra_mid_game = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED,
            }
            if message in roach_hydra_mid_game:
                self.ack(message)
                # Don't change the build if we're rushing to brood lords
                if self.build_stage != BuildStages.LATE_GAME and \
                        Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH not in self.builds:
                    self.add_build(Builds.MID_GAME_ROACH_HYDRA_LURKER)

            # Messages indicating we need to rush up to brood lords in midgame asap
            broodlord_rush_mid_game = {
                Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD,}
            if message in broodlord_rush_mid_game:
                self.ack(message)
                if self.build_stage != BuildStages.LATE_GAME:
                    self.add_build(Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH)

            # Stop townhall and worker production during defending
            large_defense = {
                Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES,}
            if message in large_defense:
                self.ack(message)
                self.stop_townhall_production = True
                self.stop_worker_production = True

            # Stop townhall and worker production for a short duration
            stop_non_army_production = {
                Messages.ENEMY_MOVING_OUT_SCOUTED}
            if message in stop_non_army_production:
                self.ack(message)

                self._stop_nonarmy_production.add(
                    True, self.bot.state.game_loop, expiry=20)

            # Restart townhall and worker production when defending stops
            exit_state = {Messages.STATE_EXITED,}
            if message in exit_state:
                self.ack(message)
                if val == ForcesStates.DEFENDING:
                    self.stop_townhall_production = False
                    self.stop_worker_production = False

    def parse_special_build_target(self,
                                   unit: builds.SpecialBuildTarget,
                                   existing_unit_counts: Counter,
                                   build_order_counts: Counter) -> Union[const.UnitTypeId, const.UpgradeId]:

        """
        Parses a SpecialBuildTarget `unit` and performs relevant mutations on
        `build_order_counts`

        :returns A build target id if it's applicable, else returns None
        """

        assert(isinstance(unit, builds.SpecialBuildTarget))

        if isinstance(unit, builds.AtLeast):
            # AtLeast is a "special" unittype that only adds 1 if we
            # don't have AT LEAST `n` number of units built.

            at_least = unit
            unit = at_least.unit_type
            amount_required = at_least.n

            if existing_unit_counts[unit] < amount_required:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(unit, existing_unit_counts, build_order_counts)
                else:
                    build_order_counts[unit] = amount_required
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.IfHasThenBuild):
            # IfHasThenBuild is a "special" unittype that only adds `n`
            # unit_type if we have AT LEAST 1 number
            # of if_has_then_build.conditional_unit_type.

            if_has_then_build = unit
            unit = if_has_then_build.unit_type
            conditional_unit_type = if_has_then_build.conditional_unit_type
            amount_to_add = if_has_then_build.n

            if existing_unit_counts[conditional_unit_type] >= 1:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(unit, existing_unit_counts, build_order_counts)
                else:
                    build_order_counts[unit] += amount_to_add
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.IfHasThenDontBuild):
            # IfHasThenDontBuild is a "special" unittype that only adds `n`
            # unit_type if we have 0 of `conditional_unit_type`.

            if_has_then_dont_build = unit
            unit = if_has_then_dont_build.unit_type
            conditional_unit_type = if_has_then_dont_build.conditional_unit_type
            amount_to_add = if_has_then_dont_build.n

            if existing_unit_counts[conditional_unit_type] == 0:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(unit, existing_unit_counts, build_order_counts)
                else:
                    build_order_counts[unit] += amount_to_add
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.OneForEach):
            # OneForEach is a "special" unittype that adds a unittype of
            # `unit_type` to the build queue for each unit_type of `for_each_unit_type`
            # that we already have created.

            one_for_each = unit
            unit = one_for_each.unit_type
            for_each_unit_type = one_for_each.for_each_unit_type

            try:
                existing_for_each_units = existing_unit_counts[for_each_unit_type]
            except IndexError:
                existing_for_each_units = 0

            if existing_for_each_units:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(unit, existing_unit_counts, build_order_counts)
                else:
                    build_order_counts[unit] += existing_for_each_units
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.CanAfford):
            # CanAfford is a "special" unittype that adds a unittype of
            # `unit_type` to the build queue only if we can afford it

            can_afford = unit
            unit = can_afford.unit_type

            if isinstance(unit, builds.SpecialBuildTarget):
                result = self.parse_special_build_target(unit, existing_unit_counts, build_order_counts)
                if self.can_afford(result):
                    return result
            elif self.can_afford(unit):
                build_order_counts[unit] += 1
                return unit
            else:
                return unit

        elif isinstance(unit, builds.PullWorkersOffVespeneUntil):
            # PullWorkersOffVespeneUntil is a "special" unittype that pulls `n`
            # workers off vespene until `unit_type` is constructed

            pull_workers_off_vespene_until = unit
            unit = pull_workers_off_vespene_until.unit_type
            amount_of_workers_to_mine = pull_workers_off_vespene_until.n
            special_id = pull_workers_off_vespene_until.id

            if existing_unit_counts[unit]:
                # Return workers to vespene mining
                if special_id in self.active_special_build_target_ids:
                    self.active_special_build_target_ids.discard(special_id)
                    self.publish(Messages.PULL_WORKERS_OFF_VESPENE, None)
                return None
            else:
                # Pull workers off vespene
                if special_id not in self.active_special_build_target_ids:
                    self.active_special_build_target_ids.add(special_id)
                    self.publish(Messages.PULL_WORKERS_OFF_VESPENE, amount_of_workers_to_mine)
                return None

        elif isinstance(unit, builds.PublishMessage):
            # PublishMessage is a "special" unittype that publishes a message
            # the first time this build target is hit

            publish_message = unit
            message = publish_message.message
            value = publish_message.value
            special_id = publish_message.id

            if special_id not in self.active_special_build_target_ids:
                self.active_special_build_target_ids.add(special_id)
                self.publish(message, value)

            return None

    def overlord_is_build_target(self) -> bool:
        """
        Build Overlords automatically once the bot has built three or more
        Overlords
        """

        # Only build overlords if we haven't yet reached max supply
        if self.bot.supply_cap < 200:
            # Subtract supply from damaged overlords. Assume we'll lose them.
            overlords = self.bot.units(
                {const.OVERLORD, const.UnitTypeId.OVERLORDTRANSPORT, const.UnitTypeId.OVERSEER})
            damaged_overlord_supply = 0
            if overlords.exists:
                damaged_overlords = overlords.filter(lambda o: o.health_percentage < 0.85)
                if damaged_overlords.exists:
                    damaged_overlord_supply = len(damaged_overlords) * 8  # Overlords provide 8 supply

            # Calculate the supply coming from overlords in eggs
            overlord_egg_count = self.bot.already_pending(const.OVERLORD)
            overlord_egg_supply = overlord_egg_count * 8  # Overlords provide 8 supply

            supply_left = self.bot.supply_left + overlord_egg_supply - damaged_overlord_supply

            if supply_left < 2 + self.bot.supply_cap / 10:
                # With a formula like this, At 20 supply cap it'll build an overlord
                # when you have 5 supply left. At 40 supply cap it'll build an overlord
                # when you have 7 supply left. This seems reasonable.

                # Ensure we have over 3 overlords.
                if len(overlords) >= 3:
                    return True

        return False

    def current_build_targets(self, n_targets=6) -> List[const.UnitTypeId]:
        """
        Goes through the build order one by one counting up all the units and
        stopping once we hit a unit we don't yet have.

        `n_targets` specifies the number of build targets to return.
        """

        build_targets = []

        if self.overlord_is_build_target():
            unit = const.OVERLORD
            self.last_build_target = self.build_target
            self.build_target = unit
            return [unit]

        # Count of existing units {unit.type_id: count}
        existing_unit_counts = Counter(map(lambda unit: unit.type_id, self.bot.units))

        # Count of units being trained or built
        pending_units = Counter({u: self.bot.already_pending(u, all_units=True) for u in const2.ZERG_UNITS})

        # Add an extra zergling for each zergling in an egg
        zergling_creation_ability = self.bot._game_data.units[const.ZERGLING.value].creation_ability
        zergling_eggs = Counter({
            const.ZERGLING: sum(
                [egg.orders[0].ability == zergling_creation_ability
                 for egg in self.bot.units(const.UnitTypeId.EGG)]
            )
        })

        # Burrowed Zerglings count as zerglings
        burrowed_zergling = Counter({const.ZERGLING: len(self.bot.units(const.ZERGLINGBURROWED))})

        # Burrowed Banelings count as banelings
        burrowed_banelings = Counter({const.BANELING: len(self.bot.units(const.BANELINGBURROWED))})

        # Burrowed Roaches count as roaches
        burrowed_roaches = Counter({const.ROACH: len(self.bot.units(const.ROACHBURROWED))})

        # Burrowed Lurkers count as lurkers
        burrowed_lurkers = Counter({const.LURKERMP: len(self.bot.units(const.LURKERMPBURROWED))})

        # Burrowed Infestors count as infestors
        burrowed_infestors = Counter({const.INFESTOR: len(self.bot.units(const.INFESTORBURROWED))})

        # Hives count as Lairs. This is a weird one that doesn't make a lot of sense
        # Reasoning is that when we get a Hive, we don't want the AI to act like we don't have a Lair
        hives_as_lairs = Counter({const.LAIR: len(self.bot.units(const.HIVE))})

        # Uprooted spine crawlers count as spine crawlers
        spine_crawlers_uprooted = Counter({const.SPINECRAWLER: len(
            self.bot.units(const.UnitTypeId.SPINECRAWLERUPROOTED))})

        # Uprooted spore crawlers count as spine crawlers
        spore_crawlers_uprooted = Counter({const.SPORECRAWLER: len(
            self.bot.units(const.UnitTypeId.SPORECRAWLERUPROOTED))})

        # Extractors without vespene left
        empty_extractors = Counter({const.EXTRACTOR: len(
            self.bot.units(const.EXTRACTOR).filter(lambda extr: extr.vespene_contents == 0))
        })

        # Count of pending upgrades
        existing_and_pending_upgrades = Counter({u: math.ceil(self.bot.already_pending_upgrade(u))
                                                 for u in const2.ZERG_UPGRADES})

        existing_unit_counts += pending_units
        existing_unit_counts += zergling_eggs
        existing_unit_counts += burrowed_zergling
        existing_unit_counts += burrowed_banelings
        existing_unit_counts += burrowed_roaches
        existing_unit_counts += burrowed_lurkers
        existing_unit_counts += burrowed_infestors
        existing_unit_counts += hives_as_lairs
        existing_unit_counts += spine_crawlers_uprooted
        existing_unit_counts += spore_crawlers_uprooted
        existing_unit_counts -= empty_extractors  # Subtract empty extractors
        existing_unit_counts += existing_and_pending_upgrades

        # Set the number of hatcheries to be the number of town halls with minerals left
        # (We want to count Lairs and Hives as hatcheries too. They're all expansions)
        townhalls = self.bot.townhalls
        if townhalls.exists:
            townhall_count = 0
            for townhall in townhalls:
                minerals = self.bot.state.mineral_field
                if minerals.exists:
                    nearby_minerals = minerals.closer_than(10, townhall)
                    if nearby_minerals.exists:
                        townhall_count += 1

            existing_unit_counts[const.HATCHERY] = townhall_count

        # Count of units in build order up till this point {unit.type_id: count}
        build_order_counts = Counter()

        # Go through each build looking for the unit we don't have
        for build in self.builds:
            if build is None:
                return []

            build_queue = builds.BUILD_MAPPING[build]

            for unit_i in range(len(build_queue)):
                unit = build_queue[unit_i]

                # Count each unit in the queue as we loop through them
                # Check if the unit is a special conditional unittype
                if isinstance(unit, builds.SpecialBuildTarget):
                    result = self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts)
                    if result is not None:
                        unit = result
                else:
                    build_order_counts[unit] += 1

                # Check if we have enough of this unit built already
                if existing_unit_counts[unit] < build_order_counts[unit]:

                    # Check if we have the tech requirement for this unit built already
                    tech_requirement = None
                    idle_building_structure = None
                    if isinstance(unit, const.UnitTypeId):
                        # Check for unit tech requirements
                        tech_requirement = self.bot._game_data.units[unit.value].tech_requirement
                        idle_building_structure = None
                    elif isinstance(unit, const.UpgradeId):
                        # Check for upgrade tech requirements
                        tech_requirement = const2.ZERG_UPGRADES_TO_TECH_REQUIREMENT[unit]
                        idle_building_structure = self.bot.units(const2.ZERG_UPGRADES_TO_STRUCTURE[unit]).ready.idle

                    # Skip worker and townhall build targets if these flags are set
                    if (self.stop_townhall_production or
                            self._stop_nonarmy_production.contains(True, self.bot.state.game_loop)) and \
                            unit in const2.UNUPGRADED_TOWNHALLS:
                        first_tier_production_structures = {const.SPAWNINGPOOL, const.GATEWAY, const.BARRACKS}
                        if self.bot.units(first_tier_production_structures):
                            continue
                    elif (self.stop_worker_production or
                            self._stop_nonarmy_production.contains(True, self.bot.state.game_loop)) and \
                            unit in const2.WORKERS:
                        first_tier_production_structures = {const.SPAWNINGPOOL, const.GATEWAY, const.BARRACKS}
                        if self.bot.units(first_tier_production_structures):
                            continue

                    if (tech_requirement is None or existing_unit_counts[tech_requirement]) > 0 and \
                            (idle_building_structure is None or idle_building_structure.exists):

                        # Found build target
                        self.last_build_target = self.build_target
                        self.build_target = unit

                        build_stage = builds.get_build_stage(build)
                        if build_stage != self.build_stage and build_targets == []:
                            # Update build stage
                            self.build_stage = build_stage
                            self.publish(Messages.NEW_BUILD_STAGE, build_stage)

                        # Return early if the next build target is a town hall.
                        # This prevents sending worker to create townhall before
                        # its time
                        if unit in const2.TOWNHALLS:
                            if not build_targets:
                                return [unit]
                            else:
                                return build_targets

                        # Add the build target
                        build_targets.append(unit)

                        # Pretend like we have this unit already and see if
                        # there are more units we can add to the build_targets list
                        existing_unit_counts[unit] += 1

                        # If we have enough build targets, return.
                        if len(build_targets) == n_targets:
                            return build_targets


        return build_targets

    async def create_build_target(self, build_target) -> bool:
        """
        Main function that issues commands to build a build order target

        Returns a boolean indicating if the build was a success
        """

        if self.last_build_target != build_target:
            self.print("Build target: {}".format(build_target))

        # Check type of unit we're building to determine how to build

        if build_target == const.HATCHERY:
            expansion_locations = await self.bot.get_open_expansions()
            try:
                expansion_location = expansion_locations[self.next_expansion_index]
            except IndexError:
                self.print("Couldn't build expansion. All spots are taken.")
                return False

            if self.can_afford(build_target):
                drones = self.bot.units(const.DRONE)
                if drones.exists:
                    drone = drones.closest_to(expansion_location)

                    err = await self.bot.do(drone.build(build_target, expansion_location))

                    if err:
                        # Try the next expansion location
                        self.print("Error while building the expansion at {}. "
                                   "Trying the next expansion location. ".format(expansion_location))
                        self.next_expansion_index += 1
                    else:
                        # Expansion worked! Reset expansion index.
                        self.next_expansion_index = 0
                        return True

            # Move drone to expansion location before construction
            elif self.bot.state.common.minerals > 200 and \
                    not self._recent_commands.contains(
                        BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop):
                if expansion_location:
                    drones = self.bot.units(const.DRONE)
                    if drones.exists:
                        nearest_drone = self.bot.units(const.DRONE).closest_to(expansion_location)
                        # Only move the drone to the expansion location if it's far away
                        # To keep from constantly issuing move commands
                        if nearest_drone.distance_to(expansion_location) > 9:
                            self.bot.actions.append(nearest_drone.move(expansion_location))

                            self.publish(Messages.DRONE_LEAVING_TO_CREATE_HATCHERY, nearest_drone.tag)

                            # Keep from issuing another expand move command
                            self._recent_commands.add(
                                BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop, expiry=22)

        elif build_target == const.LAIR:
            # Get a hatchery
            hatcheries = self.bot.units(const.HATCHERY)

            # Train the unit
            if self.can_afford(build_target) and hatcheries.exists:
                hatchery = hatcheries.closest_to(self.bot.start_location)
                self.bot.actions.append(hatchery.build(build_target))
                return True

        elif build_target == const.HIVE:
            # Get a lair
            lairs = self.bot.units(const.LAIR)

            # Train the unit
            if self.can_afford(build_target) and lairs.exists:
                self.bot.actions.append(lairs.random.build(build_target))
                return True

        elif build_target == const.EXTRACTOR:
            if self.can_afford(build_target):
                townhalls = self.bot.townhalls.ready
                for townhall in townhalls:
                    extractors = self.bot.units(const2.VESPENE_REFINERIES)
                    geysers = self.bot.state.vespene_geyser.filter(lambda g: extractors.closer_than(0.5, g).empty)
                    geyser = geysers.closest_to(townhall)

                    if geyser.distance_to(townhall) > 9:
                        continue

                    drone = self.bot.workers.closest_to(geyser)

                    self.bot.actions.append(drone.build(build_target, geyser))

                    return True

        elif build_target == const.GREATERSPIRE:
            # Get a spire
            spire = self.bot.units(const.SPIRE).idle

            # Train the unit
            if spire.exists and self.can_afford(build_target):
                self.bot.actions.append(spire.random.build(build_target))

                return True

        elif build_target == const.SPINECRAWLER:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    enemy_start_location = self.bot.enemy_start_location
                    townhall = townhalls.random
                    nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                    nearby_ramp = townhall.position.towards(
                        enemy_start_location, 1).closest(nearby_ramps)

                    if nearby_ramp.distance_to(townhall) < 18:
                        target = nearby_ramp
                    else:
                        near_townhall = townhall.position.towards_with_random_angle(
                            enemy_start_location, 10, max_difference=(math.pi / 2.0))
                        target = near_townhall

                    position = await self.bot.find_placement(
                        const.SPINECRAWLER, target, max_distance=25)

                    await self.bot.build(build_target, near=position)

                    return True

        elif build_target == const.SPORECRAWLER:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    spore_crawlers = self.bot.units(const.SPORECRAWLER)

                    if spore_crawlers.exists:
                        # Attempt to find a townhall with no sporecrawlers
                        for townhall in townhalls:
                            nearest_sc = spore_crawlers.closest_to(townhall)
                            distance_to_sc = townhall.distance_to(nearest_sc)
                            if distance_to_sc > 10:
                                break
                    else:
                        townhall = townhalls.random

                    location = townhall.position
                    nearest_minerals = self.bot.state.mineral_field.closer_than(8, townhall)
                    nearest_gas = self.bot.state.vespene_geyser.closer_than(8, townhall)
                    nearest_resources = nearest_minerals | nearest_gas

                    if nearest_resources.exists:

                        towards_resources = townhall.position.towards_with_random_angle(
                            nearest_resources.center, 2)
                        location = towards_resources

                    await self.bot.build(build_target, near=location)

                    return True

        elif build_target in const2.ZERG_STRUCTURES_FROM_DRONES:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    townhall = townhalls.closest_to(self.bot.start_location)
                    location = townhall.position

                    # Attempt to build the structure away from the nearest minerals
                    nearest_minerals = self.bot.state.mineral_field.closer_than(8, townhall)
                    nearest_gas = self.bot.state.vespene_geyser.closer_than(8, townhall)
                    nearest_resources = nearest_minerals | nearest_gas
                    if nearest_resources.exists:

                        away_from_resources = townhall.position.towards_with_random_angle(
                            nearest_resources.center, random.randint(-13, -2),
                            max_difference=(math.pi / 2.8),
                        )
                        location = away_from_resources

                    await self.bot.build(build_target, near=location)

                    return True

        elif build_target == const.QUEEN:

            townhalls = self.bot.townhalls.idle

            if self.can_afford(build_target) and townhalls.exists:
                self.bot.actions.append(
                    townhalls.random.train(build_target))

                return True

        elif build_target in const2.ZERG_UNITS_FROM_LARVAE:
            # Get a larvae
            larvae = self.bot.units(const.LARVA)

            # Train the unit
            if self.can_afford(build_target) and larvae.exists:
                if build_target == const.OVERLORD:
                    # Keep from issuing another overlord build command too soon
                    # Overlords are built in 18 seconds.
                    self._recent_commands.add(
                        BuildManagerCommands.BUILD_OVERLORD, self.bot.state.game_loop, expiry=18)

                self.bot.actions.append(larvae.random.train(build_target))
                return True

        elif build_target == const.BANELING:
            # Get a zergling
            zerglings = self.bot.units(const.ZERGLING)

            # Train the unit
            if self.can_afford(build_target) and zerglings.exists:
                # Prefer idle zerglings if they exist
                idle_zerglings = zerglings.idle
                if idle_zerglings.exists:
                    zerglings = idle_zerglings

                zergling = zerglings.closest_to(self.bot.start_location)
                self.bot.actions.append(zergling.train(build_target))
                return True

        elif build_target == const.RAVAGER:
            # Get a Roach
            roaches = self.bot.units(const.ROACH)

            # Train the unit
            if self.can_afford(build_target) and roaches.exists:
                # Prefer idle zerglings if they exist
                idle_roaches = roaches.idle
                if idle_roaches.exists:
                    roaches = idle_roaches

                roach = roaches.closest_to(self.bot.start_location)
                self.bot.actions.append(roach.train(build_target))
                return True

        elif build_target == const.LURKERMP:
            # Get a hydralisk
            hydralisks = self.bot.units(const.HYDRALISK)

            # Train the unit
            if self.can_afford(build_target) and hydralisks.exists:
                # Prefer idle hydralisks if they exist
                idle_hydralisks = hydralisks.idle
                if idle_hydralisks.exists:
                    hydralisks = idle_hydralisks

                hydralisk = hydralisks.closest_to(self.bot.start_location)
                self.bot.actions.append(hydralisk.train(build_target))
                return True

        elif build_target == const.BROODLORD:
            # Get a Corruptor
            corruptors = self.bot.units(const.CORRUPTOR)

            # Train the unit
            if self.can_afford(build_target) and corruptors.exists:
                # Prefer idle corruptors if they exist
                idle_corruptors = corruptors.idle
                if idle_corruptors.exists:
                    corruptors = idle_corruptors

                corruptor = corruptors.closest_to(self.bot.start_location)
                self.bot.actions.append(corruptor.train(build_target))
                return True

        elif build_target == const.OVERSEER:
            # Get an overlord
            overlords = self.bot.units(const.OVERLORD)

            # Train the unit
            if self.can_afford(build_target) and overlords.exists:
                overlord = overlords.closest_to(self.bot.start_location)
                self.bot.actions.append(overlord.train(build_target))
                return True

        # Upgrades below
        elif isinstance(build_target, const.UpgradeId):
            upgrade_structure_type = const2.ZERG_UPGRADES_TO_STRUCTURE[build_target]
            upgrade_structures = self.bot.units(upgrade_structure_type).ready
            if self.can_afford(build_target) and upgrade_structures.exists:

                # Prefer idle upgrade structures
                if upgrade_structures.idle.exists:
                    upgrade_structures = upgrade_structures.idle

                upgrade_ability = self.bot._game_data.upgrades[build_target.value].research_ability.id
                self.bot.actions.append(upgrade_structures.first(upgrade_ability))

                # Send out message about upgrade started
                self.publish(Messages.UPGRADE_STARTED, build_target)

                return True

        else:
            self.print("Could not determine how to create build_target `{}`".format(build_target))

        return False

    async def create_build_targets(self, build_targets: list) -> bool:
        """
        Creates a list of build targets, stopping at the first one that is
        unable to be built. Returns a boolean indicating if they were all
        built
        """

        for build_target in build_targets:
            result = await self.create_build_target(build_target)
            if not result:
                return False

        return True

    async def run(self):
        # Read messages and act on them
        await self.read_messages()

        if self.bot.minerals > 24:
            # Get the current build target
            current_build_targets = self.current_build_targets()

            if not current_build_targets:
                # If we are at the end of the build queue, then add a default build
                self.add_next_default_build()
            else:
                # Build the current build targets
                await self.create_build_targets(current_build_targets)


class ResourceManager(Manager):
    """
    Class for handling resource management. Involves:

    * Worker harvester management
    * Queen injection
    * Queen creep spread
    * Tumor creep spread
    """

    name = 'Resource Manager'

    def __init__(self, bot):
        super(ResourceManager, self).__init__(bot)

        self._recent_commands = ExpiringList()

        # Townhall tag -> Queen tag mapping of what queens belong to what townhalls
        self._townhall_queens = {}

        # Sets the number of workers to mine vespene gas per geyser
        self._ideal_vespene_worker_count: Optional[int] = None

        # Message subscriptions
        self.subscribe(Messages.NEW_BUILD)
        self.subscribe(Messages.UPGRADE_STARTED)
        self.subscribe(Messages.PULL_WORKERS_OFF_VESPENE)

    async def init(self):
        # Send all workers to the closest mineral patch
        self.initialize_workers()

    def initialize_workers(self):
        minerals = self.bot.state.mineral_field
        for worker in self.bot.workers:
            mineral = minerals.closest_to(worker)
            self.bot.actions.append(worker.gather(mineral))

    async def manage_mineral_saturation(self):
        """
        Balances mineral saturation so that no patch is oversaturated with
        workers
        """
        # Get saturated and unsaturated townhalls
        saturated_townhalls = self.bot.townhalls.filter(
            lambda th: th.assigned_harvesters > th.ideal_harvesters)

        if not saturated_townhalls:
            return

        unsaturated_townhalls = self.bot.townhalls.filter(
            lambda th: th.assigned_harvesters < th.ideal_harvesters)

        if not unsaturated_townhalls:
            return

        # Move excess worker off saturated minerals to unsaturated minerals
        for saturated_townhall in saturated_townhalls:
            mineral_workers = self.bot.workers.filter(
                lambda worker: worker.is_carrying_minerals)
            if mineral_workers.exists:
                worker = mineral_workers.closest_to(saturated_townhall)
                unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
                mineral = self.bot.state.mineral_field.closest_to(unsaturated_townhall)

                self.bot.actions.append(worker.gather(mineral, queue=True))

    async def manage_minerals(self):
        await self.manage_mineral_saturation()

        # Move idle workers to mining
        for worker in self.bot.workers.idle:
            townhalls = self.bot.townhalls
            if not townhalls.exists: return
            townhall = townhalls.closest_to(worker.position)
            mineral = self.bot.state.mineral_field.closest_to(townhall)

            self.bot.actions.append(worker.gather(mineral))

    async def manage_vespene(self):
        # If we have over 5 times the vespene than we do minerals, hold off on gas
        if self.bot.vespene > 350 and self.bot.minerals > 50 \
                and self.bot.vespene / self.bot.minerals > 6 and \
                not self._recent_commands.contains(
                    ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                    self.bot.state.game_loop):

            self._recent_commands.add(
                ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                self.bot.state.game_loop, expiry=30)

        saturated_extractors = self.bot.units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters > (self._ideal_vespene_worker_count or extr.ideal_harvesters)).ready

        unsaturated_extractors = self.bot.units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters < (self._ideal_vespene_worker_count or extr.ideal_harvesters)).ready

        if self._recent_commands.contains(
                ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE, self.bot.state.game_loop):
            # We're currently pulling workers off of vespene gas
            vespene_workers = self.bot.workers.filter(
                lambda worker: worker.is_carrying_vespene)

            for worker in vespene_workers:
                # Get saturated and unsaturated townhalls
                unsaturated_townhalls = self.bot.townhalls.filter(
                    lambda th: th.assigned_harvesters < th.ideal_harvesters)

                if unsaturated_townhalls.exists:
                    unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
                    mineral = self.bot.state.mineral_field.closest_to(unsaturated_townhall)

                    self.bot.actions.append(worker.gather(mineral, queue=True))

        else:
            # Move workers from saturated extractors to minerals
            for saturated_extractor in saturated_extractors:
                vespene_workers = self.bot.workers.filter(
                    lambda worker: worker.is_carrying_vespene)

                if not vespene_workers.exists:
                    break

                worker = vespene_workers.closest_to(saturated_extractor)

                # Get saturated and unsaturated townhalls
                unsaturated_townhalls = self.bot.townhalls.filter(
                    lambda th: th.assigned_harvesters < th.ideal_harvesters)

                if unsaturated_townhalls.exists:
                    unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
                    mineral = self.bot.state.mineral_field.closest_to(unsaturated_townhall)

                    self.bot.actions.append(worker.gather(mineral, queue=True))

            # Move workers from minerals to unsaturated extractors
            if unsaturated_extractors:
                extractor = unsaturated_extractors.first

                mineral_workers = self.bot.workers.filter(
                    lambda worker: worker.is_carrying_minerals)

                if mineral_workers.exists:
                    worker = mineral_workers.closest_to(extractor)

                    self.bot.actions.append(worker.gather(extractor, queue=True))

    async def manage_resources(self):
        """
        Manage idle workers
        """

        await self.manage_minerals()
        await self.manage_vespene()

    async def do_transfuse(self):
        queens = self.bot.units(const.QUEEN)

        for queen in queens:
            if queen.energy >= 50:
                nearby_units = self.bot.units.closer_than(15, queen)
                if nearby_units.exists:
                    nearby_units = nearby_units.sorted(lambda u: u.health_percentage)

                nearby_unit = nearby_units[0]

                # Don't transfuse yourself, fucking asshole.
                if (nearby_unit.tag == queen.tag) and len(nearby_units) > 1:
                    nearby_unit = nearby_units[1]

                if nearby_unit.health_percentage < 0.6 and nearby_unit.type_id != const.ZERGLING:
                    self.bot.actions.append(queen(const.TRANSFUSION_TRANSFUSION, nearby_unit))

    async def manage_queens(self):
        queens = self.bot.units(const.QUEEN)
        townhalls = self.bot.townhalls

        await self.do_transfuse()

        if queens.exists:
            for townhall in townhalls:
                queen_tag = self._townhall_queens.get(townhall.tag)

                if queen_tag is None:
                    # Tag a queen to the townhall
                    untagged_queens = queens.tags_not_in(self._townhall_queens.values())
                    if untagged_queens:
                        queen = untagged_queens[0]
                        self._townhall_queens[townhall.tag] = queen.tag
                    else:
                        # No queens available for this townhall. Continue to next townhall
                        continue
                else:
                    queen = queens.find_by_tag(queen_tag)

                    if queen is None:
                        # Queen died! Untag it
                        del self._townhall_queens[townhall.tag]
                    else:
                        if queen.is_idle:
                            # Move queen to its townhall
                            if queen.distance_to(townhall) > 15:
                                self.bot.actions.append(
                                    queen.attack(townhall.position))

                            if queen.energy >= 25:
                                abilities = await self.bot.get_available_abilities(queen)

                                creep_tumors = self.bot.units({const.CREEPTUMOR, const.CREEPTUMORBURROWED})

                                # Get creep tumors nearby the closest townhall
                                nearby_creep_tumors = creep_tumors.closer_than(17, townhall)

                                # If there are no nearby creep tumors or any at all, then spawn a creep tumor
                                if not nearby_creep_tumors.exists and \
                                        not self._recent_commands.contains(
                                            ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                            self.bot.state.game_loop):

                                    # Spawn creep tumor if we have none
                                    if const.BUILD_CREEPTUMOR_QUEEN in abilities:
                                        position = townhall.position.towards_with_random_angle(
                                            self.bot.enemy_start_location, random.randint(5, 7))

                                        self._recent_commands.add(
                                            ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                            self.bot.state.game_loop, expiry=50)

                                        self.bot.actions.append(queen(const.BUILD_CREEPTUMOR_QUEEN, position))

                                else:
                                    # Inject larvae
                                    if const.EFFECT_INJECTLARVA in abilities:
                                        if not townhall.has_buff(const.QUEENSPAWNLARVATIMER):
                                            self.bot.actions.append(queen(const.EFFECT_INJECTLARVA, townhall))

    async def manage_creep_tumors(self):
        creep_tumors = self.bot.units({const.CREEPTUMORBURROWED})

        for tumor in creep_tumors:
            abilities = await self.bot.get_available_abilities(tumor)
            if const.BUILD_CREEPTUMOR_TUMOR in abilities:
                position = tumor.position.towards_with_random_angle(
                    self.bot.enemy_start_location, random.randint(9, 11),
                    max_difference=(math.pi / 2.2))

                # Spawn creep tumors away from expansion locations
                if position.distance_to_closest(self.bot.expansion_locations.keys()) > 5:
                    self.bot.actions.append(tumor(const.BUILD_CREEPTUMOR_TUMOR, position))

    async def read_messages(self):
        for message, val in self.messages.items():

            upgrade_started = {Messages.UPGRADE_STARTED}
            if message in upgrade_started:
                # Ling speed started. Pull workers off vespene
                if val == const.UpgradeId.ZERGLINGMOVEMENTSPEED:
                    self.ack(message)

                    self._recent_commands.add(
                        ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                        self.bot.state.game_loop, expiry=100)

            new_build = {Messages.NEW_BUILD}
            if message in new_build:
                # Early game pool first defense started. Pull workers off vespene.
                if val == builds.EARLY_GAME_POOL_FIRST_DEFENSIVE:
                    self.ack(message)

                    self._recent_commands.add(
                        ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                        self.bot.state.game_loop, expiry=80)

            pull_workers_off_vespene = {Messages.PULL_WORKERS_OFF_VESPENE}
            if message in pull_workers_off_vespene:
                # Pull `n` workers off vespene, or set them back to working
                self.ack(message)

                self._ideal_vespene_worker_count = val

    async def run(self):
        await super(ResourceManager, self).run()

        await self.read_messages()

        await self.manage_resources()
        await self.manage_queens()
        await self.manage_creep_tumors()


class OverlordManager(StatefulManager):

    name = 'Overlord Manager'

    def __init__(self, bot):
        super(OverlordManager, self).__init__(bot)

        self.state = OverlordStates.INITIAL
        self.previous_state = None

        # Map of functions to do depending on the state
        self.state_map = {
            OverlordStates.INITIAL: self.do_initial,
            OverlordStates.INITIAL_BACKOUT: self.do_initial_backout,
            OverlordStates.INITIAL_DIVE: self.do_initial_dive,
            OverlordStates.SUICIDE_DIVE: self.do_suicide_dive,
        }

        self.state_start_map = {
            OverlordStates.INITIAL_BACKOUT: self.start_initial_backout,
            OverlordStates.INITIAL_DIVE: self.start_initial_dive,
        }

        # Overlords used for scouting
        # These must be added to the set in scouting_overlord_tags()
        self.scouting_overlord_tag = self.bot.units(const.OVERLORD).first.tag
        self.proxy_scouting_overlord_tag = None
        self.third_expansion_scouting_overlord_tag = None
        self.baneling_drop_overlord_tag = None

        # Flag for if we find an enemy proxy or rush
        self.enemy_proxy_found = False
        self.proxy_search_concluded = False

        # Tags of overlords with creep turned on
        self.overlord_tags_with_creep_turned_on = set()

        # Message subscriptions
        self.subscribe(Messages.OVERLORD_SCOUT_2_TO_ENEMY_RAMP)

    @property
    def scouting_overlord_tags(self):
        return {self.scouting_overlord_tag,
                self.proxy_scouting_overlord_tag,
                self.third_expansion_scouting_overlord_tag,
                self.baneling_drop_overlord_tag}

    async def read_messages(self):
        for message, val in self.messages.items():

            # Move proxy scouting overlord to see enemy's main ramp
            move_overlord_scout_to_enemy_ramp = {
                Messages.OVERLORD_SCOUT_2_TO_ENEMY_RAMP}
            if message in move_overlord_scout_to_enemy_ramp:
                self.ack(message)

                if self.proxy_scouting_overlord_tag is not None:
                    overlords = self.bot.units(const.OVERLORD)
                    if overlords.exists:
                        overlord = overlords.find_by_tag(self.proxy_scouting_overlord_tag)
                        if overlord:
                            # Move them to the nearest ramp

                            ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                            nearby_ramp = self.bot.enemy_start_location.towards(
                                self.bot.start_location, 6).closest(ramps)

                            target = nearby_ramp.towards(self.bot.start_location, 10.5)
                            self.bot.actions.append(overlord.move(target))

    async def turn_on_generate_creep(self):
        # Spread creep on last scouted expansion location like a fucking dick head
        if self.bot.units({const.LAIR, const.HIVE}).exists:
            overlords = self.bot.units(const.OVERLORD)
            if overlords.exists:
                for overlord in overlords.filter(
                        lambda o: o.tag not in self.overlord_tags_with_creep_turned_on):
                    self.overlord_tags_with_creep_turned_on.add(overlord.tag)
                    self.bot.actions.append(
                        overlord(const.AbilityId.BEHAVIOR_GENERATECREEPON))

    async def overlord_dispersal(self):
        """
        Disperse Overlords evenly around base
        """
        overlords = self.bot.units(const.OVERLORD).filter(
            lambda o: o.tag not in self.scouting_overlord_tags).idle

        distance = self.bot.start_location_to_enemy_start_location_distance * 0.5
        for overlord in overlords:
            target = self.bot.start_location.towards_with_random_angle(
                self.bot.enemy_start_location, distance, max_difference=(math.pi / 1.0))
            self.bot.actions.append(overlord.move(target))

    async def proxy_scout_with_second_overlord(self):
        overlords = self.bot.units(const.OVERLORD)

        if self.proxy_scouting_overlord_tag is None:
            if len(overlords) == 2:
                overlord = overlords.filter(lambda ov: ov.tag not in self.scouting_overlord_tags).first
                self.proxy_scouting_overlord_tag = overlord.tag

                expansion_location = await self.bot.get_next_expansion()

                overlord_mov_pos_1 = expansion_location.towards(self.bot.enemy_start_location, +12)
                overlord_mov_pos_2 = expansion_location.towards(self.bot.enemy_start_location, -4)

                # Move Overlord around the natural expansion
                self.bot.actions.append(overlord.move(overlord_mov_pos_1, queue=True))
                self.bot.actions.append(overlord.move(overlord_mov_pos_2, queue=True))

                # Move Overlord around different expansion locations
                expansion_locations = self.bot.get_expansion_positions()
                for expansion_location in expansion_locations[2:5]:
                    self.bot.actions.append(overlord.move(expansion_location, queue=True))

                try:
                    # This is the expected enemy 5th expand location
                    enemy_fifth_expansion = expansion_locations[-5]
                    self.bot.actions.append(overlord.move(enemy_fifth_expansion, queue=True))
                    self.bot.actions.append(overlord.stop(queue=True))
                except IndexError:
                    # The indexed expansion doesn't exist
                    pass
        else:
            if not self.enemy_proxy_found and not self.proxy_search_concluded and overlords.exists:
                scouting_overlord = overlords.find_by_tag(self.proxy_scouting_overlord_tag)
                if scouting_overlord:
                    # Report enemy proxies
                    enemy_structures = self.bot.known_enemy_structures
                    if enemy_structures.closer_than(65, self.bot.start_location).exists:
                        self.enemy_proxy_found = True
                        self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY)

                    # Report enemy ground rushes
                    enemy_units = self.bot.known_enemy_units.not_structure.not_flying
                    if enemy_units.exists:
                        nearby_enemy_units = enemy_units.exclude_type(
                            const2.ENEMY_NON_ARMY).closer_than(150, self.bot.start_location)
                        enemy_workers = nearby_enemy_units.of_type(const2.WORKERS)
                        nearby_enemy_units = nearby_enemy_units - enemy_workers
                        if enemy_workers.exists and len(enemy_workers) > 2:
                            if enemy_workers.center.distance_to(self.bot.enemy_start_location) > 70:
                                # Found enemy worker rush
                                self.enemy_proxy_found = True
                                self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH)
                        elif len(nearby_enemy_units) > 1:
                            if nearby_enemy_units.center.distance_to(self.bot.enemy_start_location) > 65:
                                # Found enemy non-worker rush
                                self.enemy_proxy_found = True
                                self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH)

                    # End early scouting process if we've reached the enemy expansion and
                    # haven't seen proxies
                    expansion_locations = self.bot.get_expansion_positions()
                    try:
                        # This is the expected enemy 5th expand location where the overlord is headed
                        enemy_fifth_expansion = expansion_locations[-5]
                        if scouting_overlord.distance_to(enemy_fifth_expansion) < 8:
                            self.proxy_search_concluded = True
                            self.publish(Messages.OVERLORD_SCOUT_FOUND_NO_RUSH)

                    except IndexError:
                        # The indexed expansion doesn't exist
                        pass

                else:
                    # Overlord has died :(
                    self.proxy_scouting_overlord_tag = None

    async def scout_enemy_third_expansion_with_third_overlord(self):
        overlords = self.bot.units(const.OVERLORD)

        if self.third_expansion_scouting_overlord_tag is None:
            if len(overlords) == 3:
                overlord = overlords.filter(lambda ov: ov.tag not in self.scouting_overlord_tags).first
                self.third_expansion_scouting_overlord_tag = overlord.tag

                enemy_expansion_locations = self.bot.get_enemy_expansion_positions()
                third_and_fourth_expansions = enemy_expansion_locations[2:4]

                # Move Overlord around different expansion locations
                for expansion_location in third_and_fourth_expansions:
                    self.bot.actions.append(overlord.move(expansion_location, queue=True))

    async def overlord_flee(self):
        """
        Flee overlords when they're damaged
        """
        dont_flee_tags = {self.baneling_drop_overlord_tag}

        overlords = self.bot.units(const.OVERLORD).tags_not_in(dont_flee_tags)

        for overlord in overlords:
            if overlord.health_percentage != 1:
                nearby_enemy_units = self.bot.units.enemy.\
                    closer_than(10, overlord).filter(lambda unit: unit.can_attack_air)

                if nearby_enemy_units.exists:
                    nearby_enemy_unit = nearby_enemy_units.closest_to(overlord)
                    away_from_enemy = overlord.position.towards(nearby_enemy_unit, -1)
                    self.bot.actions.append(overlord.move(away_from_enemy))

    async def baneling_drops(self):
        """
        Initializes a baneling drop

         * Upgrade ventrical sacks
         * Upgrade overlord and save its tag
         * Load banelings
         * Move Overlord to nearest corner of map
         * Move Overlord to adjacent corner of map
         * Move Overlord to enemy start location
         * Unload banelings
        """

        # Ensure we have Ventrical Sacks upgraded
        if const.OVERLORDSPEED in self.bot.state.upgrades \
                and self.bot.units(const.BANELINGNEST).exists:
            # Get overlords
            overlords = self.bot.units(const.UnitTypeId.OVERLORD).ready.\
                tags_not_in(self.scouting_overlord_tags)
            overlord_transports = self.bot.units(const.UnitTypeId.OVERLORDTRANSPORT).ready. \
                tags_not_in(self.scouting_overlord_tags - {self.baneling_drop_overlord_tag})

            if self.baneling_drop_overlord_tag is None:
                if overlord_transports.exists:
                    # Tag an overlord transport to drop with
                    self.print("Tagging overlord transport for a baneling drop")
                    overlord = overlord_transports.closest_to(self.bot.start_location)
                    self.baneling_drop_overlord_tag = overlord.tag
                elif overlords.exists:
                    # Morph to transport overlord
                    self.print("Morphing Overlord for baneling drop")
                    overlord = overlords.closest_to(self.bot.start_location)
                    self.baneling_drop_overlord_tag = overlord.tag
                    self.bot.actions.append(overlord(const.MORPH_OVERLORDTRANSPORT))
            else:
                # Get our overlord transport by tag
                overlord = overlord_transports.find_by_tag(self.baneling_drop_overlord_tag)
                if overlord is None:
                    # Overlord has died, continue on (rest his soul)
                    self.print("Baneling dropping overlord has died")
                    self.baneling_drop_overlord_tag = None
                elif overlord.cargo_used < overlord.cargo_max:
                    # Load banelings
                    banelings = self.bot.units(const.BANELING)
                    if len(banelings) > 3:
                        self.print("Loading banelings for baneling drop")
                        baneling = banelings.closest_to(overlord)

                        # Add baneling to harassing group so it won't attack
                        self.bot.occupied_units.add(baneling.tag)

                        self.bot.actions.append(baneling.move(overlord.position))
                        self.bot.actions.append(overlord(
                            const.AbilityId.LOAD_OVERLORD, baneling, queue=True))

                elif overlord.is_idle:
                    # Move to enemy
                    self.print("Moving transport overlord for baneling drop")
                    corners = self.bot.rect_corners(
                        self.bot._game_info.playable_area)
                    closest_corner = overlord.position.closest(corners)
                    closest_corner_to_enemy = self.bot.enemy_start_location.closest(corners)
                    adjacent_corners = self.bot.adjacent_corners(
                        self.bot._game_info.playable_area, closest_corner)
                    closest_adjacent_to_enemy = \
                        self.bot.enemy_start_location.closest(adjacent_corners)

                    if closest_corner_to_enemy == closest_adjacent_to_enemy:
                        # Move straight to enemy and drop
                        towards_enemy = self.bot.enemy_start_location.towards(
                            self.bot.start_location, 3)
                        self.bot.actions.append(overlord.move(
                            towards_enemy, queue=True))
                        self.bot.actions.append(overlord(
                            const.AbilityId.UNLOADALLAT_OVERLORD, overlord, queue=True))
                        self.bot.actions.append(overlord.move(
                            self.bot.enemy_start_location, queue=True))
                        self.bot.actions.append(overlord.move(
                            self.bot.start_location, queue=True))
                    else:
                        # Move around the corners of the map and drop
                        corner_towards_enemy = closest_adjacent_to_enemy.towards(
                            self.bot.enemy_start_location, 30)
                        self.bot.actions.append(overlord.move(
                            corner_towards_enemy))
                        towards_enemy = self.bot.enemy_start_location.towards(
                            closest_adjacent_to_enemy, 3)
                        self.bot.actions.append(overlord.move(
                            towards_enemy, queue=True))
                        self.bot.actions.append(overlord(
                            const.AbilityId.UNLOADALLAT_OVERLORD, overlord, queue=True))
                        self.bot.actions.append(overlord.move(
                            self.bot.enemy_start_location, queue=True))
                        self.bot.actions.append(overlord.move(
                            self.bot.start_location, queue=True))
                else:
                    # Drop banelings if near enemy workers or about to die
                    enemy_priorities = const2.WORKERS | {
                        const.MARINE, const.PHOENIX, const.VIKING, const.MISSILETURRET}
                    enemy_targets = self.bot.known_enemy_units.of_type(enemy_priorities).\
                        closer_than(9, overlord)
                    if len(enemy_targets) > 6:
                        self.print("Unloading banelings on enemy workers")
                        self.bot.actions.append(overlord(
                            const.AbilityId.UNLOADALLAT_OVERLORD, overlord))
                        self.bot.actions.append(overlord.move(
                            enemy_targets.center))
                        towards_start_location = overlord.position.towards(
                            self.bot.start_location, 40)
                        self.bot.actions.append(overlord.move(
                            towards_start_location, queue=True))

                    elif overlord.health_percentage < 0.7:
                        self.print("Unloading banelings from damaged Overlord")
                        self.bot.actions.append(overlord(
                            const.AbilityId.UNLOADALLAT_OVERLORD, overlord))
                        target = utils.towards_direction(overlord.position, overlord.facing, +4)
                        self.bot.actions.append(overlord.move(
                            target))
                        towards_start_location = overlord.position.towards(
                            self.bot.start_location, 40)
                        self.bot.actions.append(overlord.move(
                            towards_start_location, queue=True))

    async def do_initial(self):
        """
        We haven't seen any enemy structures yet.
        Move towards enemy's natural expansion.
        """
        await self.overlord_flee()

        # Early game scouting

        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            # Move towards natural expansion
            self.bot.actions.append(overlord.move(enemy_natural_expansion))

    async def start_initial_backout(self):
        """
        We've seen enemy structures
        Retreat from their natural expansion
        """

        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            # Move in closer towards main
            away_from_enemy_natural_expansion = \
                enemy_natural_expansion.position.towards(self.bot.start_location, +28)
            self.bot.actions.append(overlord.move(away_from_enemy_natural_expansion))

    async def do_initial_backout(self):
        await self.overlord_flee()

    async def do_suicide_dive(self):
        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            self.bot.actions.append(
                overlord.move(self.bot.enemy_start_location, queue=True))

    async def start_initial_dive(self):
        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            self.bot.actions.append(
                overlord.move(self.bot.enemy_start_location.position))

    async def do_initial_dive(self):
        await self.overlord_flee()

    async def determine_state_change(self):
        if self.state == OverlordStates.INITIAL:
            enemy_structures = self.bot.known_enemy_structures
            enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

            overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
            if overlord:
                distance_to_expansion = overlord.distance_to(enemy_natural_expansion)

                if distance_to_expansion < 40:
                    # Take note of enemy defensive structures sited
                    enemy_defensive_structures_types = {const.PHOTONCANNON, const.SPINECRAWLER, const.MISSILETURRET}
                    nearby_enemy_defensive_structures = enemy_structures.of_type(
                        enemy_defensive_structures_types).closer_than(15, overlord)
                    if nearby_enemy_defensive_structures.exists:
                        closest_enemy_defensive_structure = \
                            nearby_enemy_defensive_structures.closest_to(overlord)
                        self.publish(
                            Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                            value=closest_enemy_defensive_structure.position)

                        await self.change_state(OverlordStates.INITIAL_BACKOUT)

                if distance_to_expansion < 11:
                    if enemy_structures.closer_than(12, overlord).exists and \
                            self.bot.is_visible(enemy_natural_expansion):
                        # Check if they took their natural expansion
                        enemy_townhalls = enemy_structures.of_type(const2.TOWNHALLS)
                        if enemy_townhalls.exists:
                            if enemy_townhalls.closer_than(4, enemy_natural_expansion):
                                self.publish(Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN)
                            else:
                                self.publish(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)
                        else:
                            self.publish(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)
                        self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                        await self.change_state(OverlordStates.INITIAL_BACKOUT)
                    else:
                        await self.change_state(OverlordStates.INITIAL_DIVE)

        elif self.state == OverlordStates.INITIAL_BACKOUT:
            # If we didn't find an enemy proxy/rush, and the search is off
            # Then suicide dive in to get more information
            if not self.enemy_proxy_found and self.proxy_search_concluded:
                if len(self.bot.known_enemy_structures) < 4:
                    await self.change_state(OverlordStates.SUICIDE_DIVE)

        elif self.state == OverlordStates.INITIAL_DIVE:
            enemy_structures = self.bot.known_enemy_structures
            overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
            if overlord:
                distance_to_enemy_start_location = overlord.distance_to(self.bot.enemy_start_location)
                if distance_to_enemy_start_location < 25:
                    # Take note of enemy defensive structures sighted
                    enemy_defensive_structures_types = {const.PHOTONCANNON, const.SPINECRAWLER}
                    nearby_enemy_defensive_structures = enemy_structures.of_type(
                        enemy_defensive_structures_types).closer_than(15, overlord)
                    if nearby_enemy_defensive_structures.exists:
                        closest_enemy_defensive_structure = \
                            nearby_enemy_defensive_structures.closest_to(overlord)
                        self.publish(
                            Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                            value=closest_enemy_defensive_structure.position)

                    # Take note of enemy rush structures/units sighted

                    barracks_count = len(enemy_structures.of_type(const.BARRACKS)) > 1
                    gateway_count = len(enemy_structures.of_type(const.GATEWAY)) > 1
                    zergling_count = len(self.bot.known_enemy_units.of_type(const.ZERGLING)) > 5

                    if barracks_count or gateway_count or zergling_count:
                        self.publish(Messages.FOUND_ENEMY_EARLY_AGGRESSION)

                if enemy_structures.closer_than(11, overlord).exists:
                    self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                    await self.change_state(OverlordStates.INITIAL_BACKOUT)

                    enemy_townhalls = enemy_structures.of_type(const2.TOWNHALLS)
                    if enemy_townhalls.exists:
                        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()
                        if enemy_townhalls.closer_than(4, enemy_natural_expansion).exists:
                            self.publish(Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN)
                    else:
                        self.publish(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)

                elif distance_to_enemy_start_location < 10:
                    self.publish(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
                    await self.change_state(OverlordStates.INITIAL_BACKOUT)

        elif self.state == OverlordStates.SUICIDE_DIVE:
            pass

    async def run(self):
        await super(OverlordManager, self).run()

        await self.read_messages()

        await self.overlord_dispersal()
        await self.turn_on_generate_creep()
        await self.proxy_scout_with_second_overlord()
        await self.scout_enemy_third_expansion_with_third_overlord()
        await self.baneling_drops()


class ForceManager(StatefulManager):
    """
    State-machine for controlling forces

    States need a few things to work

    * They need a `do` function in self.state_map for them to do something each frame.
    * They need conditions defined in self.determine_state_change to switch into that state
    * Optionally they can also have a `stop` function in self.state_stop_map which runs
      when that state is exited.
    """

    name = 'Force Manager'

    def __init__(self, bot):
        super(ForceManager, self).__init__(bot)

        # Default starting state
        self.state = ForcesStates.HOUSEKEEPING

        # The previous state
        self.previous_state = self.state

        # Map of functions to do depending on the state
        self.state_map = {
            ForcesStates.HOUSEKEEPING: self.do_housekeeping,
            ForcesStates.ESCORTING: self.do_escorting,
            ForcesStates.DEFENDING: self.do_defending,
            ForcesStates.MOVING_TO_ATTACK: self.do_moving_to_attack,
            ForcesStates.ATTACKING: self.do_attacking,
            ForcesStates.SEARCHING: self.do_searching,
        }

        # Map of functions to do when entering the state
        self.state_start_map = {
            ForcesStates.ATTACKING: self.start_attacking,
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
            ForcesStates.DEFENDING: self.stop_defending,
            ForcesStates.ATTACKING: self.stop_attacking,
        }

        # Expiring list of recent commands issued
        self._recent_commands = ExpiringList()

        # List of workers that we're escorting to build Hatcheries
        self.escorting_workers = ExpiringList()

        # Army value needed to do an attack. Changes with the current build stage.
        self.army_value_to_attack = \
            self.get_army_value_to_attack(BuildStages.OPENING)

        # The army must be closer to the moving_to_attack position than this
        # in order to start an attack
        self.distance_to_moving_to_attack = \
            self.get_army_center_distance_to_attack(BuildStages.OPENING)

        # Last enemy army position seen
        self.last_enemy_army_position = None

        # Flag to set if we've published a message about defending against multiple
        # enemies since we last switched to the DEFENDING state
        self.published_defending_against_multiple_enemies = False

        # Set of worker ids of workers defending an attack.
        self.workers_defending = set()

        # Set of banelings attacking mineral lines
        self.banelings_harassing = set()

        # Set of roaches attacking mineral lines
        self.roaches_harassing = set()

        # Subscribe to messages
        self.subscribe(Messages.NEW_BUILD_STAGE)
        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
        self.subscribe(Messages.DRONE_LEAVING_TO_CREATE_HATCHERY)

    def get_army_value_to_attack(self, build_stage):
        """Given a build stage, returns the army value needed to begin an attack"""
        return {
            BuildStages.OPENING: 2,  # Assume rush. Attack with whatever we've got.
            BuildStages.EARLY_GAME: 18,  # Only attack if we banked up some units early on
            BuildStages.MID_GAME: 55,  # Attack when a sizeable army is gained
            BuildStages.LATE_GAME: 75,  # Attack when a sizeable army is gained
        }[build_stage]

    def get_army_center_distance_to_attack(self, build_stage):
        """
        Based on the build stage, we may want to allow attacking when fewer or
        more units have met up at the moving_to_attack position.
        """
        return {
            BuildStages.OPENING: 60,  # Allow greater distances for rush
            BuildStages.EARLY_GAME: 5,
            BuildStages.MID_GAME: 5,
            BuildStages.LATE_GAME: 5,
        }[build_stage]

    def get_target(self):
        """Returns enemy target to move nearby during moving_to_attack"""
        enemy_structures = self.bot.known_enemy_structures

        # Get target to attack towards
        if self.last_enemy_army_position is not None:
            # Use the location of the last seen enemy army, and group up away from that position
            target = self.last_enemy_army_position
        elif enemy_structures.exists:
            # Use enemy structure
            target = enemy_structures.closest_to(self.bot.start_location).position
        else:
            # Use enemy start location
            target = self.bot.enemy_start_location.position

        return target

    def get_nearby_to_target(self, target):
        """
        Gets a point nearby the target.
        The point is 2/3rds the distance between our starting location and the target.
        """

        return target.towards(self.bot._game_info.map_center, +32)

    async def update_enemy_army_position(self):
        enemy_units = self.bot.known_enemy_units.not_structure.exclude_type(
            const2.WORKERS | const2.ENEMY_NON_ARMY)

        # Set the last enemy army position if we see it
        if len(enemy_units) > 3:
            enemy_position = enemy_units.center.rounded

            if self.last_enemy_army_position is None:
                self.print("Visibility of enemy army at: {}".format(enemy_position))

            self.last_enemy_army_position = enemy_position

        # Set the last enemy army position to None if we scout that location
        # and see no army.
        if self.last_enemy_army_position is not None:
            if self.bot.is_visible(self.last_enemy_army_position):
                if enemy_units.empty or (len(enemy_units) < 3):
                    self.print("Enemy army no longer holding position: {}".format(
                        self.last_enemy_army_position))
                    self.last_enemy_army_position = None

    async def do_housekeeping(self):
        zerg_army_units = const2.ZERG_ARMY_UNITS | {const.ROACHBURROWED}

        army = self.bot.units.filter(
            lambda unit: unit.type_id in zerg_army_units).\
            tags_not_in(self.bot.occupied_units)

        townhalls = self.bot.townhalls

        if townhalls.exists:
            # Call back army that is far away
            for unit in army.idle:
                closest_townhall = townhalls.closest_to(unit)
                if closest_townhall.distance_to(unit) > 30:
                    self.bot.actions.append(unit.attack(closest_townhall.position))

            # Ensure each town hall has some army nearby
            closest_townhall = townhalls.closest_to(self.bot.enemy_start_location)
            for townhall in townhalls:

                number_of_units_to_townhall = round((len(army) / len(townhalls)) * 0.1)
                if townhall.tag == closest_townhall.tag:
                    # The closest townhall to the enemy should have more army
                    number_of_units_to_townhall = round((len(army) / len(townhalls)) * 3)

                nearby_army = army.closer_than(22, townhall.position)

                if len(nearby_army) < number_of_units_to_townhall:
                    # Move some army to this townhall
                    far_army = army.further_than(22, townhall.position)
                    if far_army.exists:
                        unit = far_army.random
                        if self.bot.known_enemy_units.closer_than(15, unit).empty:
                            # Move them to the nearest ramp
                            target = townhall.position

                            nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                            nearby_ramp = target.towards(self.bot.enemy_start_location, 4).\
                                closest(nearby_ramps)  # Ramp closest to townhall

                            if nearby_ramp.distance_to(target) < 20:
                                target = nearby_ramp

                            self.bot.actions.append(unit.attack(target))

    async def do_escorting(self):
        # Do escorting a couple times a second
        if self.bot.state.game_loop % 13 == 0:
            if self.escorting_workers.length(self.bot.state.game_loop):
                # Get first escorting worker in list
                escorting_worker_tag = self.escorting_workers.get_item(0, self.bot.state.game_loop)
                escorting_worker = self.bot.units.of_type(const2.WORKERS).find_by_tag(escorting_worker_tag)

                if escorting_worker:
                    army = self.bot.units.filter(
                        lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).\
                        tags_not_in(self.bot.occupied_units)
                    expansion_location = await self.bot.get_next_expansion()

                    # Move with worker until we get up to the expansion
                    if escorting_worker.distance_to(expansion_location) > 12:
                        position = escorting_worker.position

                    else:
                        towards_enemy = expansion_location.towards(self.bot.enemy_start_location, +8)
                        position = towards_enemy

                    for unit in army:
                        self.bot.actions.append(unit.attack(position))

    async def do_defending(self):
        """
        Defend townhalls from nearby enemies
        """

        for th in self.bot.townhalls:
            enemies_nearby = self.bot.known_enemy_units.closer_than(35, th.position)

            if enemies_nearby.exists:
                # Publish message if there are multiple enemies
                if not self.published_defending_against_multiple_enemies and \
                        len(enemies_nearby) > 4:
                    self.publish(Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES)
                    self.published_defending_against_multiple_enemies = True

                # Workers attack enemy
                ground_enemies = enemies_nearby.not_flying
                workers = self.bot.workers.closer_than(15, enemies_nearby.random.position)
                if workers.exists and ground_enemies.exists and \
                        len(workers) > len(ground_enemies):
                    for worker in workers:
                        if worker.tag in self.workers_defending:
                            # Defending workers gone idle, attack enemy
                            if worker.is_idle:
                                target = self.bot.closest_and_most_damaged(enemies_nearby, worker)
                                self.bot.actions.append(worker.attack(target.position))

                        else:
                            # Add workers to defending workers and attack nearby enemy
                            if len(self.workers_defending) <= len(ground_enemies):
                                target = self.bot.closest_and_most_damaged(enemies_nearby, worker)
                                if target:
                                    if target.type_id != const.BANELING:
                                        self.bot.actions.append(worker.attack(target.position))
                                        self.workers_defending.add(worker.tag)


                # Have queens defend
                queens = self.bot.units(const.QUEEN)
                if queens.exists:
                    if len(enemies_nearby) > 2:
                        # Try to get the most energized queens
                        defending_queens = queens.filter(
                            lambda q: q.energy > 49
                        )
                        if not defending_queens.exists:
                            # If no energized queens, just get the closest queens
                            defending_queens = queens.sorted(
                                lambda q: q.distance_to(enemies_nearby.center)).take(
                                3, require_all=False)
                    else:
                        # Only send the closest queen if the enemy is only a single unit
                        defending_queens = [queens.closest_to(
                            enemies_nearby.random.position)]

                    for queen in defending_queens:
                        target = self.bot.closest_and_most_damaged(enemies_nearby, queen)

                        if target and queen.distance_to(target) > 8:
                            if target.distance_to(queen) < queen.ground_range:
                                # Target
                                self.bot.actions.append(queen.attack(target))
                            else:
                                # Position
                                self.bot.actions.append(queen.attack(target.position))

                # Have army defend
                army = self.bot.units.filter(
                    lambda u: u.type_id in const2.ZERG_ARMY_UNITS)

                # The harder we're attacked, the further-out army to pull back
                if len(enemies_nearby) < 5:
                    army.closer_than(self.bot.start_location_to_enemy_start_location_distance * 0.6,
                                     self.bot.enemy_start_location)

                for unit in army:

                    target = self.bot.closest_and_most_damaged(enemies_nearby, unit)

                    if target and unit.weapon_cooldown <= 0:
                        self.bot.actions.append(unit.attack(target.position))

            # Bring back defending workers that have drifted too far from town halls
            workers_defending_to_remove = set()
            for worker_id in self.workers_defending:
                worker = self.bot.workers.find_by_tag(worker_id)
                if worker:
                    nearest_townhall = self.bot.townhalls.closest_to(worker.position)
                    if worker.distance_to(nearest_townhall.position) > 45:
                        workers_defending_to_remove.add(worker_id)
                        self.bot.actions.append(worker.move(nearest_townhall.position))
                else:
                    workers_defending_to_remove.add(worker_id)

            # Remove workers from defending set
            self.workers_defending -= workers_defending_to_remove

    async def stop_defending(self):
        # Cleanup workers that were defending and send them back to their townhalls
        for worker_id in self.workers_defending:
            worker = self.bot.workers.find_by_tag(worker_id)
            if worker:
                nearest_townhall = self.bot.townhalls.closest_to(worker.position)
                self.bot.actions.append(worker.move(nearest_townhall.position))
        self.workers_defending.clear()  # Remove worker ids from set

        # Reset flag saying that we're defending against multiple enemies
        self.published_defending_against_multiple_enemies = False

    async def do_moving_to_attack(self):
        army_units = const2.ZERG_ARMY_UNITS

        army = self.bot.units.filter(
            lambda unit: unit.type_id in army_units).\
            tags_not_in(self.bot.occupied_units)

        if not army.exists:
            return

        main_target = self.get_target()

        # Get target to attack towards
        nearby_target = self.get_nearby_to_target(main_target)

        # Search for another spot to move to
        # if not self.bot.in_pathing_grid(nearby_target):
        nearby_target = self.bot.find_nearby_pathable_point(nearby_target)

        for unit in army:
            self.bot.actions.append(unit.attack(nearby_target))

    async def start_attacking(self):
        # Command for when attacking starts
        self._recent_commands.add(ForceManagerCommands.START_ATTACKING, self.bot.state.game_loop, expiry=4)

        # Do Baneling harass during attack
        banelings = self.bot.units(const.BANELING)\
            .tags_not_in(self.bot.occupied_units)
        if banelings.exists:
            # Take 4 banelings if we have 4, otherwise just don't harass
            # This returns a list (not a Units Group)
            try:
                harass_banelings: List = banelings.take(4, True)
            except AssertionError:
                # This SHOULD only happen if we don't have 4 banelings
                harass_banelings = []
            if harass_banelings:
                enemy_structures = self.bot.known_enemy_structures

                if enemy_structures.exists:
                    # Get expansion locations starting from enemy start location
                    enemy_townhalls = enemy_structures.of_type(
                        const2.TOWNHALLS)

                    if enemy_townhalls.exists:
                        # Get the enemy townhall that we know of that is the furthest away from
                        # the closest enemy structure we know of. Hopefully this means they attack
                        # far away from where the main army will be attacking
                        enemy_townhall = enemy_townhalls.furthest_to(
                            enemy_structures.closest_to(self.bot.start_location))

                        for baneling in harass_banelings:
                            target = enemy_townhall
                            self.bot.actions.append(baneling.move(target.position))
                            self.banelings_harassing.add(baneling.tag)

            # Burrow banelings
            burrowed_banelings = self.bot.units(const.BANELINGBURROWED)
            # Only burrow up to six banelings at a time
            if const.BURROW in self.bot.state.upgrades and \
                    (not burrowed_banelings.exists or len(burrowed_banelings) < 4):
                # Get the banelings that aren't harassing mineral lines
                banelings = banelings.tags_not_in(self.banelings_harassing)

                if len(banelings) >= 4:
                    # Get two banelings
                    banelings = banelings[:2]

                    army = self.bot.units.filter(
                        lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)
                    if army.exists:
                        for baneling in banelings:
                            # Consider them harassing banelings for the moment
                            self.banelings_harassing.add(baneling.tag)

                            # Move them to a nearest ramp near the army center and burrow them
                            target = army.center

                            nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                            nearby_ramp = target.closest(nearby_ramps)  # Ramp closest to army

                            if nearby_ramp.distance_to(target) < 14:
                                target = nearby_ramp

                            self.bot.actions.append(baneling.move(target))
                            self.bot.actions.append(
                                baneling(const.AbilityId.BURROWDOWN_BANELING, queue=True))

        # Do burrow roach harass during attack
        roaches = self.bot.units(const.ROACH)
        if roaches.exists and const.BURROW in self.bot.state.upgrades and \
                const.UpgradeId.TUNNELINGCLAWS in self.bot.state.upgrades:
            # Get the roaches that aren't harassing mineral lines
            roaches = roaches.tags_not_in(self.roaches_harassing)

            if len(roaches) >= 4:
                # Get two roaches
                roaches = roaches[:2]

                enemy_structures = self.bot.known_enemy_structures
                if enemy_structures.exists:
                    # Get expansion locations starting from enemy start location
                    enemy_townhalls = enemy_structures.of_type(
                        const2.TOWNHALLS)

                    if enemy_townhalls.exists:
                        # Get the enemy townhall that we know of that is the furthest away from
                        # the closest enemy structure we know of. Hopefully this means they attack
                        # far away from where the main army will be attacking
                        enemy_townhall = enemy_townhalls.furthest_to(
                            enemy_structures.closest_to(self.bot.start_location))
                        enemy_townhall = self.bot.find_nearby_pathable_point(
                            enemy_townhall.position)

                        for roach in roaches:
                            # Consider them harassing roaches for the moment
                            self.roaches_harassing.add(roach.tag)

                            self.bot.actions.append(
                                roach(const.AbilityId.BURROWDOWN_ROACH))
                            self.bot.actions.append(roach.move(enemy_townhall, queue=True))
                            self.bot.actions.append(
                                roach(const.AbilityId.BURROWUP_ROACH, queue=True))

        # Do Mutalisk harass during attack
        mutalisks = self.bot.units(const.MUTALISK)
        if mutalisks.exists:
            dangerous_enemy_units = {const.PHOTONCANNON, const.SPORECRAWLER, const.MISSILETURRET}

            enemy_structures = self.bot.known_enemy_structures

            if enemy_structures.exists:
                # Get expansion locations starting from enemy start location
                enemy_townhalls = enemy_structures.of_type(
                    const2.TOWNHALLS).filter(
                    lambda th: enemy_structures.of_type(
                        dangerous_enemy_units).closer_than(7, th).empty)

                if enemy_townhalls.exists:
                    for mutalisk in mutalisks:
                        enemy_expansion = enemy_townhalls.random
                        self.bot.actions.append(mutalisk.move(enemy_expansion))
                else:
                    for mutalisk in mutalisks:
                        target = enemy_structures.random.position
                        self.bot.actions.append(mutalisk.move(target))

    async def stop_attacking(self):
        # Cleanup banelings that were harassing
        self.banelings_harassing.clear()

        # Cleanup roaches that were harassing
        roaches = self.bot.units(const.ROACHBURROWED)
        if roaches:
            roaches = roaches.tags_in(self.roaches_harassing)
            for roach in roaches:
                self.bot.actions.append(
                    roach(const.AbilityId.BURROWUP_ROACH))

        self.roaches_harassing.clear()

        # Reset the occupied units
        self.bot.occupied_units.clear()

    async def do_attacking(self):
        # Don't attackmove into the enemy with these units
        no_attackmove_units = {
            const.OVERSEER, const.MUTALISK, const.CORRUPTOR, const.VIPER}

        # Army units to send a couple seconds before the main army
        frontline_army_units = {const.BANELING, const.BROODLORD}

        # Unburrow idle harassing roaches
        roaches = self.bot.units(const.ROACHBURROWED)
        if roaches:
            roaches = roaches.tags_in(self.roaches_harassing).idle
            for roach in roaches:
                self.bot.actions.append(
                    roach(const.AbilityId.BURROWUP_ROACH))

        # Do main force attacking
        army = self.bot.units.filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).\
            exclude_type(no_attackmove_units).\
            tags_not_in(self.bot.occupied_units)

        # Exclude the banelings that are currently harassing
        army -= self.bot.units.tags_in(self.banelings_harassing)

        backline_army = army.exclude_type(frontline_army_units)
        frontline_army = army.of_type(frontline_army_units)

        if not army.exists:
            return

        enemy_structures = self.bot.known_enemy_structures
        if enemy_structures.exists:
            target = enemy_structures.closest_to(army.center).position
        else:
            target = self.bot.enemy_start_location

        # Hold back the backline army for a few seconds
        if not self._recent_commands.contains(
                ForceManagerCommands.START_ATTACKING, self.bot.state.game_loop):
            for unit in backline_army:
                if not unit.is_attacking and unit.weapon_cooldown <= 0:
                    self.bot.actions.append(unit.attack(target))

        # Send in the frontline army immediatelly
        for unit in frontline_army:
            if not unit.is_attacking and unit.weapon_cooldown <= 0:
                self.bot.actions.append(unit.attack(target))

    async def do_searching(self):
        army = self.bot.units.filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).\
            tags_not_in(self.bot.occupied_units).idle

        if not army.exists:
            return

        # Get expansion locations starting from enemy start location
        enemy_expansion_positions = self.bot.get_enemy_expansion_positions()

        for expansion in enemy_expansion_positions:
            for unit in army.idle:
                self.bot.actions.append(unit.move(expansion, queue=True))

    async def determine_state_change(self):
        # Reacting to subscribed messages
        for message, val in self.messages.items():
            # Start searching for an enemy location if we can't find it
            if message in {Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION}:
                if self.state != ForcesStates.DEFENDING:
                    self.ack(message)
                    return await self.change_state(ForcesStates.SEARCHING)

            if message in {Messages.DRONE_LEAVING_TO_CREATE_HATCHERY}:
                if self.state == ForcesStates.HOUSEKEEPING:
                    self.ack(message)

                    # Add the escorting worker to a list for 25 seconds
                    self.escorting_workers.add(val, iteration=self.bot.state.game_loop, expiry=25)

                    return await self.change_state(ForcesStates.ESCORTING)

            if message in {Messages.NEW_BUILD_STAGE}:
                self.ack(message)

                # Update army value required to attack
                new_army_value_to_attack = self.get_army_value_to_attack(val)
                self.army_value_to_attack = new_army_value_to_attack
                self.print("New army value to attack with: {}".format(
                    new_army_value_to_attack))

                # Update distance to moving_to_attack meetup center required to attack
                new_distance_to_moving_to_attack = self.get_army_center_distance_to_attack(val)
                self.distance_to_moving_to_attack = new_distance_to_moving_to_attack

        # HOUSEKEEPING
        if self.state == ForcesStates.HOUSEKEEPING:

            army = self.bot.units.filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            if army.exists:
                # Value of the army
                army_value = sum(const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army)

                if army_value > self.army_value_to_attack:
                    return await self.change_state(ForcesStates.MOVING_TO_ATTACK)

        # ESCORTING
        elif self.state == ForcesStates.ESCORTING:
            if not self.escorting_workers.length(self.bot.state.game_loop):
                # We've guarded the worker for long enough, change state
                return await self.change_state(ForcesStates.HOUSEKEEPING)

            elif not self.bot.units.of_type(const2.WORKERS).find_by_tag(
                    self.escorting_workers.get_item(0, self.bot.state.game_loop)):
                # The worker no longer exists. Change state
                return await self.change_state(ForcesStates.HOUSEKEEPING)

            escorting_worker_tag = self.escorting_workers.get_item(0, self.bot.state.game_loop)
            escorting_worker = self.bot.units.of_type(const2.WORKERS).find_by_tag(escorting_worker_tag)

            if escorting_worker:
                expansion_location = await self.bot.get_next_expansion()

                # Worker made it to the destination.
                if escorting_worker.distance_to(expansion_location) < 1:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

        # DEFENDING
        elif self.state == ForcesStates.DEFENDING:
            # Loop through all townhalls. If enemies are near any of them, don't change state.
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    40, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby.exists:
                    # Enemies found, don't change state.
                    break
            else:
                return await self.change_state(self.previous_state)

        # MOVING_TO_ATTACK
        elif self.state == ForcesStates.MOVING_TO_ATTACK:
            army = self.bot.units.filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            if army.exists:
                # Value of the army
                army_value = sum(const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army)

                if army_value < self.army_value_to_attack:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

                # Start attacking when army has amassed
                target = self.get_target()
                nearby_target = self.get_nearby_to_target(target)
                if army.center.distance_to(nearby_target) < self.distance_to_moving_to_attack:
                    return await self.change_state(ForcesStates.ATTACKING)

        # ATTACKING
        elif self.state == ForcesStates.ATTACKING:
            army = self.bot.units.filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            if army.exists:

                # Value of the army
                army_value = sum(const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army)

                if army_value < self.army_value_to_attack * 0.4:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

                enemy_start_location = self.bot.enemy_start_location.position
                # Start searching the map if we're at the enemy's base and can't find them.
                if army.center.distance_to(enemy_start_location) < 25 and \
                        not self.bot.known_enemy_structures.exists:

                    self.publish(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)

                    return await self.change_state(ForcesStates.SEARCHING)

        # SEARCHING
        elif self.state == ForcesStates.SEARCHING:
            enemy_structure = self.bot.known_enemy_structures
            if enemy_structure.exists:
                self.publish(Messages.ARMY_FOUND_ENEMY_BASE, value=enemy_structure.first.position)
                return await self.change_state(ForcesStates.HOUSEKEEPING)

            units_at_enemy_location = self.bot.units.closer_than(
                6, self.bot.enemy_start_location)

            if units_at_enemy_location.exists:
                self.publish(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)

        # Switching to DEFENDING from any other state
        if self.state != ForcesStates.DEFENDING:
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    30, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby.exists:
                    return await self.change_state(ForcesStates.DEFENDING)

    async def run(self):
        await super(ForceManager, self).run()

        await self.update_enemy_army_position()


class MicroManager(Manager):
    """
    Manager for microing army units
    """

    name = 'Micro Manager'

    def __init__(self, bot):
        super(MicroManager, self).__init__(bot)

        self.healing_roaches_tags = set()

        # We only want to send a single bile at each force field.
        # Tag the biled ones.
        self.biled_forcefields = set()

    async def micro_back_melee(self, unit) -> bool:
        """
        Micros back damaged melee units
        Returns a boolean indicating whether they were micro'd back

        """

        if unit.health_percentage < 0.2:
            cached_unit = self.bot.unit_cache.get(unit.tag)
            if cached_unit and cached_unit.is_taking_damage:
                if self.bot.known_enemy_units:
                    nearest_enemy = self.bot.known_enemy_units.closest_to(unit)
                    nearby_friendly_units = self.bot.units.closer_than(8, nearest_enemy)
                    if len(nearby_friendly_units) > 2 and \
                            nearest_enemy.distance_to(unit) < 6 and \
                            nearest_enemy.can_attack_ground and \
                            nearest_enemy.ground_range < 1:
                        away_from_enemy = unit.position.towards(nearest_enemy, -3)
                        self.bot.actions.append(unit.move(away_from_enemy))
                        return True
        return False

    async def manage_workers(self):
        workers = self.bot.units(const2.WORKERS)

        for worker in workers:
            await self.micro_back_melee(worker)

    async def manage_zerglings(self):
        zerglings = self.bot.units(const.ZERGLING)

        attack_priority_types = const2.WORKERS

        # Micro zerglings
        for zergling in zerglings:
            await self.micro_back_melee(zergling)

            nearby_enemy_units = self.bot.known_enemy_units.closer_than(8, zergling)
            if nearby_enemy_units:
                # Focus down priorities
                nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priority_types)
                if nearby_enemy_priorities:
                    nearby_enemy_unit = nearby_enemy_priorities.closest_to(zergling)
                    self.bot.actions.append(zergling.attack(nearby_enemy_unit))

                closest_enemy_unit = nearby_enemy_units.closest_to(zergling)
                # Micro away from banelings
                if closest_enemy_unit.type_id == const.BANELING:
                    nearby_friendly_units = self.bot.units.closer_than(3, closest_enemy_unit)
                    distance_to_enemy = zergling.distance_to(closest_enemy_unit)
                    if nearby_friendly_units:
                        closest_friendly_unit_to_enemy = nearby_friendly_units.closest_to(closest_enemy_unit)
                        if len(nearby_friendly_units) >= 1 and \
                                distance_to_enemy < 4.5 and \
                                closest_friendly_unit_to_enemy.tag != zergling.tag:
                            away_from_enemy = zergling.position.towards(closest_enemy_unit, -1)
                            self.bot.actions.append(zergling.move(away_from_enemy))

        # # Burrow zerglings near enemy townhall
        # # Decided not to use for now
        # if const.BURROW in self.bot.state.upgrades:
        #     for zergling in zerglings:
        #         nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, zergling)
        #         nearby_enemy_structures = self.bot.known_enemy_structures.closer_than(5, zergling)
        #         if nearby_enemy_structures.exists:
        #             townhalls = nearby_enemy_structures.of_type(const2.TOWNHALLS)
        #             if townhalls.exists:
        #                 nearby_enemy_detectors = nearby_enemy_structures.of_type(detector_structure_types)
        #
        #                 # Only burrow if there are no nearby detectors
        #                 if nearby_enemy_detectors.empty:
        #                     nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priority_types)
        #                     # Only burrow if there are few nearby priorities to attack
        #                     if nearby_enemy_priorities.empty or \
        #                             (nearby_enemy_priorities.exists and nearby_enemy_priorities.amount < 2):
        #
        #                         # Never burrow more than 5 zerglings at a time
        #                         if self.bot.units(const.UnitTypeId.ZERGLINGBURROWED).amount < 5:
        #                             self.bot.actions.append(zergling(const.BURROWDOWN_ZERGLING))

    async def manage_banelings(self):
        banelings = self.bot.units(const.BANELING)
        burrowed_banelings = self.bot.units(const.UnitTypeId.BANELINGBURROWED)

        attack_priorities = const2.WORKERS | {const.MARINE, const.ZERGLING, const.ZEALOT}

        # Micro banelings
        for baneling in banelings:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(9, baneling)
            if nearby_enemy_units.exists:
                nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priorities)
                if nearby_enemy_priorities.exists:
                    # Filter enemy priorities for only those that also have a nearby priority.
                    # It's only a priority if it makes the splash damage worth it.
                    nearby_enemy_priorities = nearby_enemy_priorities.filter(
                        lambda u: nearby_enemy_units.closer_than(2, u).of_type(attack_priorities).exists)

                    if nearby_enemy_priorities:
                        nearby_enemy_unit = nearby_enemy_priorities.closest_to(baneling)
                        self.bot.actions.append(baneling.attack(nearby_enemy_unit))

        # Unburrow banelings if enemy nearby
        for baneling in burrowed_banelings:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(2, baneling)
            if len(nearby_enemy_units) > 3:
                # Unburrow baneling
                self.bot.actions.append(baneling(const.BURROWUP_BANELING))

    async def manage_roaches(self):
        roaches = self.bot.units(const.ROACH)

        attack_priorities = const2.WORKERS | {const.SIEGETANK, const.UnitTypeId.SIEGETANKSIEGED}

        for roach in roaches:
            # Burrow damaged roaches
            if const.BURROW in self.bot.state.upgrades:
                if roach.health_percentage < 0.20:
                    # Move away from the direction we're facing
                    target = utils.towards_direction(roach.position, roach.facing, -20)

                    # Tag roach as a healing roach
                    self.healing_roaches_tags.add(roach.tag)

                    self.bot.actions.append(roach(const.BURROWDOWN_ROACH))
                    self.bot.actions.append(roach.move(target, queue=True))

        # Unburrow healed roaches
        to_remove_from_healing = set()
        for roach_tag in self.healing_roaches_tags:
            roach = self.bot.units.find_by_tag(roach_tag)
            if roach:
                if roach.health_percentage > 0.96:
                    nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, roach)
                    if nearby_enemy_units.empty or len(nearby_enemy_units) < 2:
                        # Untag roach as a healing roach
                        to_remove_from_healing.add(roach_tag)

                        # Unburrow roach
                        self.bot.actions.append(roach(const.BURROWUP_ROACH))
            else:
                to_remove_from_healing.add(roach_tag)

        # Remove all unburrowed roaches from healing roaches set
        for roach_tag in to_remove_from_healing:
            self.healing_roaches_tags.remove(roach_tag)

    async def manage_ravagers(self):
        ravagers = self.bot.units(const.RAVAGER)

        bile_priorities = {
            const.OVERLORD, const.MEDIVAC, const.SIEGETANKSIEGED,
            const.PHOTONCANNON, const.SPINECRAWLER, const.PYLON, const.SUPPLYDEPOT,
        }
        bile_priorities_neutral = {
            const.UnitTypeId.FORCEFIELD,
        }

        for ravager in ravagers:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(9, ravager)
            if nearby_enemy_units.exists:
                # Perform bile attacks
                # Bile range is 9
                nearby_enemy_priorities = nearby_enemy_units.of_type(bile_priorities)
                nearby_enemy_priorities = nearby_enemy_priorities | self.bot.state.units(bile_priorities_neutral)

                # Prefer targeting our bile_priorities
                nearby_enemy_priorities = nearby_enemy_priorities \
                    if nearby_enemy_priorities.exists else nearby_enemy_units

                abilities = await self.bot.get_available_abilities(ravager)
                for enemy_unit in nearby_enemy_priorities.sorted(
                        lambda unit: ravager.distance_to(unit), reverse=True):

                    can_cast = await self.bot.can_cast(ravager, const.AbilityId.EFFECT_CORROSIVEBILE,
                                                       enemy_unit.position,
                                                       cached_abilities_of_unit=abilities)
                    if can_cast:
                        our_closest_unit_to_enemy = self.bot.units.closest_to(enemy_unit)
                        if our_closest_unit_to_enemy.distance_to(enemy_unit.position) > 1:

                            # Only bile a forcefield at most once
                            if enemy_unit.type_id == const.UnitTypeId.FORCEFIELD:
                                if enemy_unit.tag in self.biled_forcefields:
                                    continue
                                self.biled_forcefields.add(enemy_unit.tag)

                            self.bot.actions.append(ravager(const.EFFECT_CORROSIVEBILE, enemy_unit.position))
                            break
                else:
                    # If we're not using bile, then micro back ravagers
                    closest_enemy = nearby_enemy_units.closest_to(ravager)
                    if ravager.weapon_cooldown and closest_enemy.distance_to(ravager) < ravager.ground_range:
                        away_from_enemy = ravager.position.towards(closest_enemy, -3)

                        distance = await self.bot._client.query_pathing(ravager, away_from_enemy)
                        if distance and distance < 5:
                            self.bot.actions.append(ravager.move(away_from_enemy))

    async def manage_mutalisks(self):
        mutalisks = self.bot.units(const.MUTALISK)

        attack_priorities = {const.QUEEN, const.SIEGETANK}

        for mutalisk in mutalisks:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(11, mutalisk)
            if nearby_enemy_units.exists:
                # Only begin concentrated targeting near enemy town halls
                if nearby_enemy_units.of_type(const2.TOWNHALLS).exists:
                    nearby_enemy_workers = nearby_enemy_units.of_type(const2.WORKERS)
                    nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priorities)
                    nearby_enemy_can_attack_air = nearby_enemy_units.filter(lambda u: u.can_attack_air)

                    # TOO MANY BADDIES. GET OUT OF DODGE
                    if len(nearby_enemy_can_attack_air) > 1:
                        towards_start_location = mutalisk.position.towards(self.bot.start_location, 80)
                        self.bot.actions.append(mutalisk.move(towards_start_location))

                    # Prefer targeting our priorities
                    if nearby_enemy_workers.exists:
                        nearby_enemy_units = nearby_enemy_workers
                    elif nearby_enemy_priorities.exists:
                        nearby_enemy_units = nearby_enemy_priorities

                    nearby_enemy_unit = nearby_enemy_units.closest_to(mutalisk)
                    self.bot.actions.append(mutalisk.attack(nearby_enemy_unit))

    async def manage_corruptors(self):
        corruptors = self.bot.units(const.CORRUPTOR)
        if corruptors.exists:
            army = self.bot.units(const2.ZERG_ARMY_UNITS)
            if army.exists:
                for corruptor in corruptors:
                    # Keep corruptor slightly ahead center of army
                    if corruptor.distance_to(army.center) > 6:
                        position = army.center.towards(self.bot.enemy_start_location, 8)
                        self.bot.actions.append(corruptor.move(position))

    async def manage_overseers(self):
        overseers = self.bot.units(const.OVERSEER)
        army = self.bot.units(const2.ZERG_ARMY_UNITS)
        for overseer in overseers:
            if overseer.energy > 50:
                abilities = await self.bot.get_available_abilities(overseer)

                # Spawn changeling
                if const.SPAWNCHANGELING_SPAWNCHANGELING in abilities:
                    self.bot.actions.append(overseer(
                        const.SPAWNCHANGELING_SPAWNCHANGELING))

            if army.exists:
                # Keep overseer slightly ahead center of army
                if overseer.distance_to(army.center) > 6:
                    position = army.center.towards(self.bot.enemy_start_location, 8)
                    self.bot.actions.append(overseer.move(position))

    async def manage_changelings(self):
        changeling_types = {
            const.CHANGELING, const.CHANGELINGMARINE, const.CHANGELINGMARINESHIELD, const.CHANGELINGZEALOT,
            const.CHANGELINGZERGLING, const.CHANGELINGZERGLINGWINGS}
        changelings = self.bot.units(changeling_types).idle

        for c in changelings:
            # Get enemy's 5 first expansions including starting location
            expansion_locations = self.bot.get_enemy_expansion_positions()
            expansion_locations = expansion_locations[0:4]
            expansion_locations.reverse()

            for expansion_location in expansion_locations:
                self.bot.actions.append(c.move(expansion_location, queue=True))

    async def manage_spine_crawlers(self):
        rooted_spine_crawlers = self.bot.units(const.SPINECRAWLER).ready
        uprooted_spine_crawlers = self.bot.units(const.SPINECRAWLERUPROOTED).ready
        spine_crawlers = rooted_spine_crawlers | uprooted_spine_crawlers
        townhalls = self.bot.townhalls.ready

        if spine_crawlers.exists:
            if townhalls.exists:
                townhall = townhalls.closest_to(self.bot.enemy_start_location)

                nearby_spine_crawlers = spine_crawlers.closer_than(25, townhall)

                # Unroot spine crawlers that are far away from the front expansions
                if not nearby_spine_crawlers.exists or (
                        len(nearby_spine_crawlers) < len(spine_crawlers) / 2):

                    for sc in rooted_spine_crawlers.idle:
                        self.bot.actions.append(sc(
                            const.AbilityId.SPINECRAWLERUPROOT_SPINECRAWLERUPROOT))

                # Root unrooted spine crawlers near the front expansions
                for sc in uprooted_spine_crawlers.idle:
                    nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                    nearby_ramp = townhall.position.towards(
                        self.bot.enemy_start_location, 2).closest(nearby_ramps)

                    if nearby_ramp.distance_to(townhall) < 18:
                        target = nearby_ramp
                    else:
                        near_townhall = townhall.position.towards_with_random_angle(
                            self.bot.enemy_start_location, 10, max_difference=(math.pi / 3.0))
                        target = near_townhall

                    position = await self.bot.find_placement(
                        const.SPINECRAWLER, target, max_distance=25)

                    self.bot.actions.append(
                        sc(const.AbilityId.SPINECRAWLERROOT_SPINECRAWLERROOT, position))

    async def manage_structures(self):
        structures = self.bot.units.structure

        # Cancel damaged not-ready structures
        for structure in structures.not_ready:
            if structure.health_percentage < 0.1 or \
                    (structure.build_progress > 0.9 and structure.health_percentage < 0.4):
                self.bot.actions.append(structure(const.CANCEL))

    async def manage_eggs(self):
        # egg_types = {const.BROODLORDCOCOON, const.RAVAGERCOCOON, const.BANELINGCOCOON,
        #              const.UnitTypeId.LURKERMPEGG, const.UnitTypeId.EGG}
        egg_types = {const.UnitTypeId.EGG}
        eggs = self.bot.units(egg_types)

        # Cancel damaged not-ready structures
        for egg in eggs:
            if egg.health_percentage < 0.4 and egg.build_progress < 0.9:
                self.bot.actions.append(egg(const.CANCEL))

    async def avoid_biles(self):
        """Avoid incoming bile attacks"""
        for bile in filter(lambda e: e.id == const.EffectId.RAVAGERCORROSIVEBILECP,
                           self.bot.state.effects):
            try:
                position = bile.positions[0]
            except IndexError:
                pass

            units = self.bot.units.closer_than(1.5, position)

            if units.exists:
                for unit in units:
                    target = position.towards(unit.position, 2)
                    self.bot.actions.append(unit.move(target))

    async def manage_combat(self, unit, attack_priorities=None):
        """Handles combat micro for the given unit"""

        if unit.weapon_cooldown or unit.is_moving:
            # Don't manage combat if we have a weapon cooldown
            return

        if attack_priorities is None:
            attack_priorities = set()

        enemy_units = self.bot.known_enemy_units
        if enemy_units:
            enemy_units = enemy_units.closer_than(unit.ground_range * 1.3, unit)
            if enemy_units:
                target = self.bot.closest_and_most_damaged(
                    enemy_units, unit, priorities=attack_priorities)
                if target:
                    self.bot.actions.append(unit.attack(target))

    async def manage_combat_micro(self):
        # Units to do default combat micro for

        # Micro closer to nearest enemy army cluster if our dps is higher
        # Micro further from nearest enemy army cluster if our dps is lower
        for army_cluster in self.bot.army_clusters:
            army_center = army_cluster.position

            nearest_enemy_cluster = army_center.closest(self.bot.enemy_clusters)
            enemy_army_center = nearest_enemy_cluster.position

            if army_center.distance_to(enemy_army_center) < 18:
                types_not_to_move = {const.LURKERMP, const.QUEEN}
                nearby_army = [u for u in army_cluster if u.type_id not in types_not_to_move]

                if nearby_army and nearest_enemy_cluster:
                    army_strength = sum(self.bot.strength_of(u) for u in nearby_army)
                    enemy_strength = sum(self.bot.strength_of(u) for u in nearest_enemy_cluster)

                    for unit in nearby_army:
                        if unit.movement_speed > 0 and \
                                unit.ground_range > 2 and \
                                unit.weapon_cooldown and \
                                not unit.is_moving:
                            nearest_enemy_unit = unit.position.closest(nearest_enemy_cluster)

                            if army_strength < enemy_strength * 0.9:
                                # Back off from enemy if our cluster is weaker
                                how_far_to_move = -6
                                away_from_enemy = unit.position.towards(
                                    nearest_enemy_unit, how_far_to_move)
                                self.bot.actions.append(unit.move(away_from_enemy))

                            # Check if nearest enemy unit is melee or ranged
                            elif 0 < nearest_enemy_unit.ground_range < 1.5:
                                if len(army_cluster) < 8 and unit.ground_range > 1:
                                    # If nearest enemy unit is melee and our cluster is small, back off
                                    how_far_to_move = -2
                                    away_from_enemy = unit.position.towards(
                                        nearest_enemy_unit, how_far_to_move)
                                    self.bot.actions.append(unit.move(away_from_enemy))
                                    self.bot.actions.append(unit.attack(unit.position, queue=True))

                            else:
                                # If nearest enemy unit is ranged
                                if army_strength > enemy_strength * 1.1:
                                    # Close the distance if our cluster is stronger
                                    distance_to_enemy_unit = unit.distance_to(nearest_enemy_unit)
                                    if distance_to_enemy_unit > unit.ground_range * 0.5:
                                        how_far_to_move = distance_to_enemy_unit * 0.6
                                        towards_enemy = unit.position.towards(
                                            nearest_enemy_unit, how_far_to_move)
                                        self.bot.actions.append(unit.move(towards_enemy))

    async def run(self):
        # Do combat priority selection
        micro_combat_unit_types = \
            {const.ZERGLING, const.ROACH, const.HYDRALISK, const.RAVAGER, const.CORRUPTOR, const.BROODLORD,
             const.LURKERMPBURROWED, const.ULTRALISK, const.SPINECRAWLER, const.SPORECRAWLER, const.QUEEN}
        units = self.bot.units(micro_combat_unit_types)
        priorities = const2.WORKERS | {const.SIEGETANK, const.SIEGETANKSIEGED, const.QUEEN, const.COLOSSUS,
                                       const.MEDIVAC, const.WARPPRISM}
        for unit in units:
            await self.manage_combat(unit, attack_priorities=priorities)

        # Do combat micro (moving closer/further away from enemy units
        await self.manage_combat_micro()

        await self.avoid_biles()
        await self.manage_workers()
        await self.manage_zerglings()
        await self.manage_banelings()
        await self.manage_roaches()
        await self.manage_ravagers()
        await self.manage_mutalisks()
        await self.manage_corruptors()
        await self.manage_overseers()
        await self.manage_changelings()
        await self.manage_spine_crawlers()
        await self.manage_structures()
        await self.manage_eggs()


class LambdaBot(sc2.BotAI):
    def __init__(self):
        super(LambdaBot, self).__init__()

        self.intel_manager = None
        self.build_manager = None
        self.resource_manager = None
        self.overlord_manager = None
        self.force_manager = None
        self.micro_manager = None

        self.managers = {}

        self.iteration = 0

        # "Do" actions to run
        self.actions = []

        # Message subscriptions
        self._message_subscriptions: Dict[const2.Messages, Manager] = defaultdict(list)

        # Global Intel
        self.enemy_start_location = None
        self.not_enemy_start_locations = None

        # Set of tags of units currently occupied in some way. Don't order them.
        # This is cleared every time an attack ends
        self.occupied_units = set()

        # Map of all our unit's tags to UnitCached objects with their remembered
        # properties (Last health, shields, location, etc)
        self.unit_cache = {}

        # Map of all our unit's tags to UnitCached objects with their remembered
        # properties (Last health, shields, location, etc)
        self.enemy_cache = {}

        # Our army clusters
        self.army_clusters = clustering.get_fresh_clusters([], n=3)

        # Our enemy clusters
        self.enemy_clusters = clustering.get_fresh_clusters([], n=2)

    async def on_step(self, iteration):
        self.iteration = iteration

        if iteration == 0:
            # Update the default builds based on the enemy's race
            builds.update_default_builds(self.enemy_race)

            # Setup Global Intel variables
            self.enemy_start_location = self.enemy_start_locations[0]
            self.not_enemy_start_locations = {self.start_location}

            # Load up managers
            self.intel_manager = IntelManager(self)
            self.build_manager = BuildManager(
                self, starting_build=BUILD)
            self.resource_manager = ResourceManager(self)
            self.overlord_manager = OverlordManager(self)
            self.force_manager = ForceManager(self)
            self.micro_manager = MicroManager(self)

            self.managers = {
                self.intel_manager,
                self.build_manager,
                self.resource_manager,
                self.overlord_manager,
                self.force_manager,
                self.micro_manager,
            }

            # Initialize managers
            for manager in self.managers:
                await manager.init()

            await self.chat_send("λ LΛMBDANAUT λ - {}".format(VERSION))

        # Update the unit cache with remembered friendly and enemy units
        self.update_unit_caches()

        await self.intel_manager.run()  # Run before all other managers

        await self.resource_manager.run()
        await self.build_manager.run()
        await self.force_manager.run()
        await self.micro_manager.run()

        # Do this more rarely. Less important. Start on third iteration.
        if iteration % 15 == 3:
            await self.overlord_manager.run()

        # Update the unit clusters
        if iteration % 8 == 0:
            self.update_clusters()

        if DEBUG:
            await self.draw_debug()

        # "Do" actions
        await self.do_actions(self.actions)

        # Reset actions
        self.actions = []

    async def on_unit_created(self, unit):
        self.publish(None, Messages.UNIT_CREATED, unit)

        # Always allow banelings to attack structures
        if unit.type_id == const.BANELING:
            self.actions.append(unit(const.BEHAVIOR_BUILDINGATTACKON))

    async def on_unit_destroyed(self, unit_tag):
        # Remove destroyed units from caches
        if unit_tag in self.unit_cache:
            del self.unit_cache[unit_tag]
        if unit_tag in self.enemy_cache:
            del self.enemy_cache[unit_tag]

    @property
    def pathable_start_location(self):
        """Pathable point near start location"""
        return self.find_nearby_pathable_point(self.start_location)

    @property
    def start_location_to_enemy_start_location_distance(self):
        return self.start_location.distance_to(self.enemy_start_location)

    async def draw_debug(self):
        """
        Draws debug images on screen during game
        """

        # # Print cluster debug info
        # print ("Army cluster count: {}".format(len([cluster for cluster in self.army_clusters if cluster])))
        # print ("Army clusters: {}".format([cluster.position for cluster in self.army_clusters]))
        # print ("Enemy cluster count: {}".format(len([cluster for cluster in self.enemy_clusters if cluster])))

        # Create units on condition
        # zerglings = self.units(const.ZERGLING)
        # if len(zerglings) > 10:
        #     await self._client.debug_create_unit([[const.ZERGLING, 15, zerglings.random.position, 2]])
        #
        # if self.iteration == 25:
        #       drones = self.units(const2.WORKERS)
        #       await self._client.debug_create_unit([[const.ZERGLING, 11, drones.random.position, 1]])
        #       await self._client.debug_create_unit([[const.ZERGLING, 15, drones.random.position, 2]])

        # Create banelings and zerglings every 15 steps
        if self.iteration % 15 == 0:
              hatch = self.units(const.HATCHERY)
              # await self._client.debug_create_unit([[const.ZERGLING, 6, hatch.random.position + Point2((11, 0)), 1]])
              # await self._client.debug_create_unit([[const.BANELING, 2, hatch.random.position + Point2((6, 0)), 2]])
              # await self._client.debug_create_unit([[const.ZERGLING, 7, hatch.random.position + Point2((6, 0)), 2]])
              # await self._client.debug_create_unit([[const.ROACH, 1, hatch.random.position + Point2((11, 0)), 1]])
              # await self._client.debug_create_unit([[const.ROACH, 2, hatch.random.position + Point2((6, 0)), 2]])

        class Green:
            r = 0
            g = 255
            b = 0

        class Red:
            r = 255
            g = 0
            b = 0

        # Draw clusters
        for cluster in self.army_clusters:
            if cluster:
                radius = cluster.position.distance_to_furthest(cluster)
                cluster_position = cluster.position.to3
                cluster_position += Point3((0, 0, 5))
                self._client.debug_sphere_out(cluster_position, radius, color=Green())

        for cluster in self.enemy_clusters:
            if cluster:
                radius = cluster.position.distance_to_furthest(cluster)
                cluster_position = cluster.position.to3
                cluster_position += Point3((0, 0, 5))
                self._client.debug_sphere_out(cluster_position, radius, color=Red())

        await self._client.send_debug()

    def update_clusters(self):
        """
        Updates the position of k-means clusters we keep of units
        """

        our_army = self.units(const2.ZERG_ARMY_UNITS)
        enemy_units = self.known_enemy_units.filter(lambda u: u.is_visible)

        if our_army:
            clustering.k_means_update(self.army_clusters, our_army)

        if enemy_units:
            clustering.k_means_update(self.enemy_clusters, enemy_units)

    def update_unit_caches(self):
        """
        Updates the friendly units and enemy units caches
        """
        for units, cache in zip((self.units, self.known_enemy_units),
                                (self.unit_cache, self.enemy_cache)):
            for unit in units:
                # If we already remember this unit
                cached_unit = cache.get(unit.tag)
                if cached_unit:

                    # Compare its health/shield since last step, to find out if it has taken any damage
                    if unit.health_percentage < cached_unit.health_percentage or \
                            unit.shield_percentage < cached_unit.shield_percentage:
                        cached_unit.is_taking_damage = True
                    else:
                        cached_unit.is_taking_damage = False

                    # Update cached unit health and shield
                    cached_unit.health_percentage = unit.health_percentage
                    cached_unit.shield_percentage = unit.shield_percentage
                    cached_unit.last_positions.append(unit.position)

                else:
                    new_cached_unit = unit_cache.UnitCached()
                    new_cached_unit.last_positions.append(unit.position)
                    cache[unit.tag] = new_cached_unit

    def publish(self, manager, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Publish a message of message_type to all subscribers.
        """
        for subscriber in self._message_subscriptions[message_type]:
            if subscriber is not manager:
                subscriber.inbox(message_type, value)

    def subscribe(self, manager, message_type):
        """Subscribes a manager to a type of message"""
        self._message_subscriptions[message_type].append(manager)

    def unsubscribe(self, manager, message_type):
        """Unsubscribes a manager to a type of message"""
        self._message_subscriptions[message_type].remove(manager)

    def can_attack(self, unit, target):
        can = (unit.can_attack_ground and not target.is_flying) or \
              (unit.can_attack_air and target.is_flying) or \
              (unit.type_id == const.BANELING and not target.is_flying)
        return can

    def get_expansion_positions(self) -> List[sc2.position.Point2]:
        """Returns our expansion positions in order from nearest to furthest"""
        expansions = self.expansion_locations.keys()
        expansion_positions = self.start_location.sort_by_distance(expansions)

        return expansion_positions

    def get_enemy_expansion_positions(self) -> List[sc2.position.Point2]:
        """Returns enemy expansion positions in order from their nearest to furthest"""

        enemy_start_location = self.enemy_start_location.position

        expansions = self.expansion_locations.keys()
        enemy_expansion_positions = enemy_start_location.sort_by_distance(expansions)

        return enemy_expansion_positions

    def get_enemy_natural_expansion(self) -> Union[None, sc2.position.Point2]:
        try:
            return self.get_enemy_expansion_positions()[1]
        except IndexError:
            return None

    async def get_open_expansions(self) -> List[Point2]:
        """Gets a sorted list of open expansions from the start location"""

        expansions = []

        start_p = self.pathable_start_location

        expansion_locations = self.expansion_locations.keys()

        sorted_expansions = await self.sort_pathing_distances_to(
            expansion_locations, start_p)

        for el in sorted_expansions:

            def is_near_to_expansion(t):
                return t.position.distance_to(el) < self.EXPANSION_GAP_THRESHOLD

            if any(map(is_near_to_expansion, self.townhalls)):
                # already taken
                continue

            d = await self._client.query_pathing(start_p, el)
            if d is None:
                continue

            expansions.append(el)

        return expansions

    async def sort_pathing_distances_to(self, l: List[Union[Point2, sc2.unit.Unit]],
                                        end_p: Union[Point2, sc2.unit.Unit]) -> List[Union[float, int]]:
        """
        Sorts each item in `l` based on its pathing distance from `end_p`

        :param l: List of units/points to sort distances from `end_p`
        :param end_p: Point/Unit to sort distances of each item in `l` from
        """

        # Zip the list together with the start point
        zipped_list = [[start_p, end_p] for start_p in l]

        distances = await self._client.query_pathings(zipped_list)

        zip_with_distances = zip(distances, l)
        zip_with_distances = sorted(zip_with_distances, key=(lambda dp: dp[0]))

        sorted_l = [p for d, p in zip_with_distances]

        return sorted_l

    def find_nearby_pathable_point(self, near: sc2.position.Point2) -> Union[None, sc2.position.Point2]:
        DISTANCE = 70
        placement_step = 5
        for distance in range(2, DISTANCE, 2):

            possible_positions = [sc2.position.Point2(p).offset(near).to2 for p in (
                [(dx, -distance) for dx in range(-distance, distance + 1, placement_step)] +
                [(dx, distance) for dx in range(-distance, distance + 1, placement_step)] +
                [(-distance, dy) for dy in range(-distance, distance + 1, placement_step)] +
                [(distance, dy) for dy in range(-distance, distance + 1, placement_step)]
            )]

            positions = [position for position in possible_positions
                         if self.in_pathing_grid(position)]

            if positions:
                return min(positions, key=lambda p: p.distance_to(near))
            else:
                return None

    def rect_corners(self, rect):
        p1 = sc2.position.Point2((rect.x, rect.y))
        p2 = p1 + sc2.position.Point2((rect.width, 0))
        p3 = p1 + sc2.position.Point2((0, rect.height))
        p4 = p1 + sc2.position.Point2((rect.width, rect.height))

        return (p1, p2, p3, p4)

    def adjacent_corners(self, rect, corner: sc2.position.Point2) -> Tuple[sc2.position.Point2]:
        """
        Returns the points of the adjacent corners of the given point in a rec
        """
        corners = self.rect_corners(rect)
        corners = corner.sort_by_distance(corners)

        # The closest corner (corners[0]) is the corner itself.
        # Get second and third closest corners
        adjacents = (corners[1], corners[2])

        return adjacents

    def closest_and_most_damaged(self, unit_group, unit, priorities=None, can_attack=True):
        """
        Gets the unit from Unitgroup who is the closest to `unit` but also the most damaged.

        Formula: ((health + shield) / 2) * distance * (1 if in priorities. 2 if not in priorities)

        :param can_attack: If true, filters `unit_group` for those that `unit` can attack
        """

        if priorities is None:
            priorities = set()

        if can_attack:
            unit_group = unit_group.filter(lambda u: self.can_attack(unit, u))

        if not unit_group:
            return

        return unit_group.sorted(lambda u: ((u.health_percentage + u.shield_percentage) / 2) * u.distance_to(unit) * (int(u not in priorities) + 1))[0]

    def strength_of(self, unit):
        """
        Returns the calculated standalone estimated strength of a unit
        """

        strength = 0

        if unit.ground_dps > 0 and unit.air_dps <= 0:
            strength = unit.ground_dps
        elif unit.air_dps > 0 and unit.ground_dps <= 0:
            strength = unit.air_dps
        else:
            strength = (unit.ground_dps + unit.air_dps) / 2

        # Arbitrarily multiply strength by 2 if they are ranged
        # TODO: Make this better
        if unit.ground_range > 1 or unit.air_range > 1:
            strength *= 2

        return strength

    def moving_closer_to(self, unit, cache, point) -> bool:
        """
        Returns true if the unit has been moving closer to POINT over all of
        its recorded positions. The unit must be represented in `cache` or
        False will be returned.

        """
        unit_cached = cache.get(unit.tag)
        if unit_cached:
            last_positions = unit_cached.last_positions

            # Only consider units we've seen their last position of
            if len(last_positions) == unit_cached.last_positions_maxlen:
                # If every point in the units last positions are closer to our start location, then
                # add one to the closer_enemy_counts
                last_position_2 = last_positions[0]
                for last_position_i in range(1, len(last_positions)):
                    last_position = last_positions[last_position_i]
                    if last_position_2.distance_to(point) <= \
                            last_position.distance_to(point):
                        break
                    last_position_2 = last_position
                else:
                    return True

        return False
