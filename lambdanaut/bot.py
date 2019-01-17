from collections import Counter, defaultdict
from itertools import takewhile
import math
import random
from typing import Any, Dict, List, Optional, Tuple, Union

import sc2
import sc2.constants as const

import lambdanaut
import lambdanaut.builds as builds
import lambdanaut.const2 as const2

from lambdanaut.const2 import Messages, BuildManagerCommands, ResourceManagerCommands, ForcesStates, OverlordStates
from lambdanaut.builds import Builds, BuildStages, BUILD_MAPPING, DEFAULT_NEXT_BUILDS
from lambdanaut.expiringlist import ExpiringList


VERSION = '3.0'
BUILD = builds.EARLY_GAME_DEFAULT_OPENER


def get_training_unit(unit):
    """
    If a hatchery is training a queen, this returns the QUEEN unit type
    If an egg is mutating a zergling, this returns the ZERGLING unit type

    TODO: This is quite hacky. I'm not sure if it'll always work.
    """

    unit_orders = unit.orders

    # If nothing is currently trained(no orders), then return None
    if not len(unit_orders):
        return None

    unit_name = unit_orders[0].ability.link_name
    unit_name = unit_name.upper()  # Uppercase the string
    unit_name.replace(" ", "")  # Remove all whitespace from string
    try:
        unit_type = getattr(const, unit_name)  # This line might fail!
    except AttributeError:
        print("=== ERROR IN get_training_unit() COULDN'T FIND CONSTANT {} IN "
              "sc2.constants === ".format(unit_type))
        return None

    return unit_type


class Manager(object):
    """
    Base class for all AI managers
    """

    name = 'Manager'

    # Managers can receive messages by subscribing to certain events
    # with self.subscribe(EVENT_NAME)

    def __init__(self, bot, build_order=None):
        self.bot = bot

        self._messages = {}

    def inbox(self, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Send a message of message_type to this manager
        """
        self._messages[message_type] = value

    @property
    def messages(self):
        return self._messages.copy()

    def ack(self, message_type):
        """
        Messages must be acknowledged to remove them from the inbox
        """
        print('{}: Message acked: {}'.format(self.name, message_type.name))
        self._messages.pop(message_type)

    def subscribe(self, message_type: const2.Messages):
        """
        Subscribe to a message of message_type
        """
        return self.bot.subscribe(self, message_type)

    def publish(self, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Publish a message to all subscribers of it's type
        """
        print('{}: Message published: {} - {}'.format(self.name, message_type.name, value))
        return self.bot.publish(self, message_type, value)

    async def read_messages(self):
        """
        Overwrite this function to read all incoming messages
        """
        pass

    async def run(self):
        raise NotImplementedError


class StatefulManager(Manager):
    """
    Base class for all state-machine AI managers
    """

    # Default starting state to set in Manager
    state = None
    # The previous state
    previous_state = None

    # Maps to overwrite with state-machine functions
    state_map = {}
    # Map of functions to do when entering the state
    state_start_map = {}
    # Map of functions to do when leaving the state
    state_stop_map = {}

    async def determine_state_change(self):
        raise NotImplementedError

    async def change_state(self, new_state):
        """
        Changes the state and runs a start and stop function if specified
        in self.state_start_map or self.state_stop_map"""

        print('{}: State changed to: {}'.format(self.name, new_state.name))

        # Run a start function for the new state if it's specified
        start_function = self.state_start_map.get(new_state)
        if start_function:
            await start_function()

        # Run a stop function for the current state if it's specified
        stop_function = self.state_stop_map.get(self.state)
        if stop_function:
            await stop_function()

        # Set the previous state to the current state
        self.previous_state = self.state

        # Set the new state
        self.state = new_state

    async def run_state(self):
        # Run function for current state
        state_f = self.state_map.get(self.state)
        if state_f is not None:
            return await state_f()

    async def run(self):
        await self.determine_state_change()
        await self.run_state()


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
                    print("{}: Couldn't find enemy base in any start location".format(self.name, ))
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

    def enemy_counter_with_roach_spotted(self):
        """Checks the map to see if there are any visible units we should counter with roach/hydra"""
        if not self.has_scouted_enemy_counter_with_roaches:
            enemy_counter_with_roach_types = {const.ROACH, const.ROACHWARREN}

            enemy_counter_with_roach_units = self.bot.known_enemy_units.of_type(enemy_counter_with_roach_types)

            if enemy_counter_with_roach_units.exists:
                self.has_scouted_enemy_counter_with_roaches = True
                return True

        return False

    def enemy_air_tech_scouted(self):
        """Checks the map to see if there are any visible enemy air tech"""
        if not self.has_scouted_enemy_air_tech:
            enemy_air_tech_types = {
                const.STARGATE, const.STARPORT, const.SPIRE,
                const.LIBERATOR, const.BATTLECRUISER, const.ORACLE, const.BANSHEE,
                const.PHOENIX, const.BROODLORD, const.DARKSHRINE, const.GHOSTACADEMY,
                const.GHOST, const.MUTALISK, const.CORRUPTOR,
                const.LURKERDEN, const.LURKER, const.UnitTypeId.ROACHBURROWED,}

            enemy_air_tech_units = self.bot.known_enemy_units.of_type(enemy_air_tech_types)

            if enemy_air_tech_units.exists:
                self.has_scouted_enemy_air_tech = True
                return True

        return False

    async def assess_game(self):
        """
        Assess the game's state and send out applicable messages
        """

        if self.enemy_air_tech_scouted():
            self.publish(Messages.ENEMY_AIR_TECH_SCOUTED)
        if self.enemy_counter_with_roach_spotted():
            self.publish(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)

    async def run(self):
        await self.read_messages()
        await self.assess_game()


class BuildManager(Manager):

    name = 'Build Manager'

    def __init__(self, bot, starting_build):
        super(BuildManager, self).__init__(bot)

        assert isinstance(starting_build, Builds)

        self.builds = [
            starting_build,
            None,
            None,
            None
        ]
        self.build_stage = builds.get_build_stage(starting_build)

        self.build_target = None
        self.last_build_target = None

        # Message subscriptions
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN)
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH)
        self.subscribe(Messages.ENEMY_AIR_TECH_SCOUTED)
        self.subscribe(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)

        # Dict with ttl so that we know what build commands were recently issued
        # For avoiding things like building two extractors when we needed 1
        # [EXTRACTOR, HATCHERY, etc. etc..]
        self._recent_build_orders = ExpiringList()

        # Recent commands issued. Uses constants defined in const2.py
        self._recent_commands = ExpiringList()

    def can_afford(self, unit):
        """Returns boolean indicating if the player has enough minerals,
        vespene, and supply to build the unit"""

        can_afford = self.bot.can_afford(unit)
        return \
            can_afford.can_afford_minerals and \
            can_afford.can_afford_vespene and \
            can_afford.have_enough_supply

    def add_build(self, build):
        print("{}: Adding build order: {}".format(self.name, build.name))

        assert isinstance(build, Builds)

        build_stage = builds.get_build_stage(build)
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
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS)

            # Messages indicating we need to defend an early aggression/rush
            defensive_early_game = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY,
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH,
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH,}
            if message in defensive_early_game:
                self.ack(message)

                # Cancel constructing hatcheries that are not near completion
                constructing_hatcheries = self.bot.units(const.HATCHERY).not_ready
                if constructing_hatcheries.exists:
                    print("{}: Cancelling all constructing hatcheries".format(self.name))
                    for hatchery in constructing_hatcheries:
                        enemy_units = self.bot.known_enemy_units
                        if enemy_units.exists:
                            nearby_enemy_units = enemy_units.closer_than(20, hatchery)
                            if nearby_enemy_units or hatchery.build_progress < 0.8:
                                self.bot.actions.append(hatchery(const.CANCEL))

                # Switch to an defensive build
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
                self.add_build(Builds.MID_GAME_ROACH_HYDRA_LURKER)

    def overlord_is_build_target(self) -> bool:
        """
        Build Overlords automatically once the bot has built three or more
        Overlords
        """

        # Subtract supply from damaged overlords. Assume we'll lose them.
        overlords = self.bot.units(const.OVERLORD)
        damaged_overlord_supply = 0
        if overlords.exists:
            damaged_overlords = overlords.filter(lambda o: o.health_percentage < 0.7)
            if damaged_overlords.exists:
                damaged_overlord_supply = damaged_overlords.amount * 8  # Overlords provide 8 supply

        # Calculate the supply coming from overlords in eggs
        overlord_egg_count = len(
            [True for egg in self.bot.units(const.EGG)
             if get_training_unit(egg) == const.OVERLORD])
        overlord_egg_supply = overlord_egg_count * 8  # Overlords provide 8 supply

        supply_left = self.bot.supply_left + overlord_egg_supply - damaged_overlord_supply

        if supply_left < 2 + self.bot.supply_cap / 10:
            # With a formula like this, At 20 supply cap it'll build an overlord
            # when you have 5 supply left. At 40 supply cap it'll build an overlord
            # when you have 7 supply left. This seems reasonable.

            # Ensure we have over 3 overlords.
            if overlords.exists and overlords.amount >= 3:
                return True

        return False

    def current_build_target(self) -> const.UnitTypeId:
        """
        Goes through the build order one by one counting up all the units and
        stopping once we hit a unit we don't yet have

        :returns Unit Type or None
        """

        if self.overlord_is_build_target():
            unit = const.OVERLORD
            self.last_build_target = self.build_target
            self.build_target = unit
            return unit

        # Count of existing units {unit.type_id: count}
        existing_unit_counts = Counter(map(lambda unit: unit.type_id, self.bot.units))

        # Units still being built in eggs (to be added to existing units counter)
        units_in_eggs = Counter([get_training_unit(egg)
                                 for egg in self.bot.units(const.EGG)])

        # Units being trained in hatcheries (to be added to existing units counter)
        units_being_trained = Counter([get_training_unit(hatchery)
                                       for hatchery in self.bot.units(const.HATCHERY)])

        # Baneling Eggs count as banelings
        baneling_eggs = Counter({const.BANELING: len(self.bot.units(const.BANELINGCOCOON))})

        # Ravager Cocoons count as ravagers
        ravager_cocoons = Counter({const.RAVAGER: len(self.bot.units(const.RAVAGERCOCOON))})

        # Lurker Eggs count as lurkers
        lurker_eggs = Counter({const.LURKER: len(self.bot.units(const.UnitTypeId.LURKEREGG))})

        # Brood Lord cocoons count as Brood Lords
        brood_lord_cocoons = Counter({const.BROODLORD: len(self.bot.units(const.UnitTypeId.BROODLORDCOCOON))})

        # Overseer cocoons count as Overseers
        overseer_cocoons = Counter({const.OVERSEER: len(self.bot.units(const.OVERLORDCOCOON))})

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

        # Count of existing upgrades
        existing_upgrades = Counter(self.bot.state.upgrades)

        existing_unit_counts += units_in_eggs
        existing_unit_counts += units_being_trained
        existing_unit_counts += baneling_eggs
        existing_unit_counts += ravager_cocoons
        existing_unit_counts += lurker_eggs
        existing_unit_counts += brood_lord_cocoons
        existing_unit_counts += overseer_cocoons
        existing_unit_counts += spine_crawlers_uprooted
        existing_unit_counts += spore_crawlers_uprooted
        existing_unit_counts -= empty_extractors  # Subtract empty extractors
        existing_unit_counts += existing_upgrades

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

        # Units recently ordered to be built.
        # Must be counted after counting the amount of townhalls to prevent
        # building multiple townhalls.
        recent_build_orders = Counter(self._recent_build_orders.items(self.bot.state.game_loop))
        existing_unit_counts += recent_build_orders

        # Count of units in build order up till this point {unit.type_id: count}
        build_order_counts = Counter()

        # Go through each build looking for the unit we don't have
        for build in self.builds:
            if build is None:
                return None

            build_queue = builds.BUILD_MAPPING[build]

            for unit in build_queue:

                if isinstance(unit, builds.AtLeast):
                    # AtLeast is a "special" unittype that only adds 1 if we
                    # don't have AT LEAST `n` number of units built

                    at_least = unit
                    unit = at_least.unit_type

                    if existing_unit_counts[unit] < at_least.n:
                        build_order_counts[unit] += 1
                else:
                    build_order_counts[unit] += 1

                if existing_unit_counts[unit] < build_order_counts[unit]:
                    # Found build target
                    self.last_build_target = self.build_target
                    self.build_target = unit

                    build_stage = builds.get_build_stage(build)
                    if build_stage != self.build_stage:
                        # Update build stage
                        self.build_stage = build_stage
                        self.publish(Messages.NEW_BUILD_STAGE, build_stage)
                        print()

                    return unit

        return None

    async def create_build_target(self, build_target):
        """
        Main function that issues commands to build a build order target
        """

        if self.last_build_target != build_target:
            print("Build target: {}".format(build_target))

        # Check type of unit we're building to determine how to build

        if build_target == const.HATCHERY:
            expansion_location = await self.bot.get_next_expansion()

            if self.can_afford(build_target):
                await self.bot.expand_now()

                # Keep from issuing another expand command for 15 seconds
                self._recent_build_orders.add(
                    build_target, iteration=self.bot.state.game_loop, expiry=15)

            # Move drone to expansion location before construction
            elif self.bot.state.common.minerals > 200 and \
                    not self._recent_commands.contains(
                        BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop):
                if expansion_location:
                    nearest_drone = self.bot.units(const.DRONE).closest_to(expansion_location)
                    # Only move the drone to the expansion location if it's far away
                    # To keep from constantly issuing move commands
                    if nearest_drone.distance_to(expansion_location) > 9:
                        self.bot.actions.append(nearest_drone.move(expansion_location))

                        # Keep from issuing another expand move command
                        self._recent_commands.add(
                            BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop, expiry=15)

        elif build_target == const.LAIR:
            # Get a hatchery
            hatcheries = self.bot.units(const.HATCHERY)

            # Train the unit
            if self.can_afford(build_target) and hatcheries.exists:
                self.bot.actions.append(hatcheries.random.build(build_target))

        elif build_target == const.HIVE:
            # Get a lair
            lairs = self.bot.units(const.LAIR)

            # Train the unit
            if self.can_afford(build_target) and lairs.exists:
                self.bot.actions.append(lairs.random.build(build_target))

        elif build_target == const.EXTRACTOR:
            if self.can_afford(build_target):
                townhall = self.bot.townhalls.filter(lambda th: th.is_ready).first
                geyser = self.bot.state.vespene_geyser.closest_to(townhall)
                drone = self.bot.workers.closest_to(geyser)

                if self.can_afford(build_target):
                    err = self.bot.actions.append(drone.build(build_target, geyser))

                    # Add structure order to recent build orders
                    if not err:
                        self._recent_build_orders.add(build_target, iteration=self.bot.state.game_loop, expiry=5)

        elif build_target == const.LURKERDEN:
            # Get a hydralisk den
            hydralisk_dens = self.bot.units(const.HYDRALISKDEN).idle

            # Train the unit
            if hydralisk_dens.exists and self.can_afford(build_target):
                self.bot.actions.append(hydralisk_dens.random.build(build_target))

        elif build_target == const.GREATERSPIRE:
            # Get a spire
            spire = self.bot.units(const.SPIRE).idle

            # Train the unit
            if spire.exists and self.can_afford(build_target):
                self.bot.actions.append(spire.random.build(build_target))

        elif build_target == const.SPINECRAWLER:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    enemy_start_location = self.bot.enemy_start_location
                    townhall = townhalls.closest_to(enemy_start_location)

                    direction_of_enemy = townhall.position.towards_with_random_angle(enemy_start_location, 10)

                    await self.bot.build(build_target, near=direction_of_enemy)

                    self._recent_build_orders.add(build_target, iteration=self.bot.state.game_loop, expiry=10)

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

                    self._recent_build_orders.add(build_target, iteration=self.bot.state.game_loop, expiry=10)

        elif build_target in const2.ZERG_STRUCTURES_FROM_DRONES:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    townhall = townhalls.first
                    location = townhall.position

                    # Attempt to build the structure away from the nearest minerals
                    nearest_minerals = self.bot.state.mineral_field.closer_than(8, townhall)
                    nearest_gas = self.bot.state.vespene_geyser.closer_than(8, townhall)
                    nearest_resources = nearest_minerals | nearest_gas
                    if nearest_resources.exists:

                        away_from_resources = townhall.position.towards_with_random_angle(
                            nearest_resources.center, random.randint(-16, -6),
                            max_difference=(math.pi / 2.1),
                        )
                        location = away_from_resources

                    err = await self.bot.build(build_target, near=location)

                    # Add structure order to recent build orders
                    if not err:
                        self._recent_build_orders.add(build_target, iteration=self.bot.state.game_loop, expiry=10)

        elif build_target == const.QUEEN:

            idle_hatcheries = self.bot.units(const.HATCHERY).idle

            if self.can_afford(build_target) and idle_hatcheries.exists:
                self.bot.actions.append(
                    idle_hatcheries.random.train(build_target))

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

        elif build_target == const.LURKER:
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

        elif build_target == const.OVERSEER:
            # Get an overlord
            overlords = self.bot.units(const.OVERLORD)

            # Train the unit
            if self.can_afford(build_target) and overlords.exists:
                overlord = overlords.closest_to(self.bot.start_location)
                self.bot.actions.append(overlord.train(build_target))

        # Upgrades below
        elif build_target in const2.ZERG_UPGRADES_TO_ABILITY:
            upgrade_structure_type = const2.ZERG_UPGRADES_TO_STRUCTURE[build_target]
            upgrade_structure = self.bot.units(upgrade_structure_type).ready.idle
            if self.can_afford(build_target) and upgrade_structure.exists:
                upgrade_ability = const2.ZERG_UPGRADES_TO_ABILITY[build_target]
                self.bot.actions.append(upgrade_structure.first(upgrade_ability))

                self._recent_build_orders.add(build_target, iteration=self.bot.state.game_loop, expiry=200)

    async def run(self):
        # Read messages and act on them
        await self.read_messages()

        # Get the current build target
        current_build_target = self.current_build_target()

        if current_build_target is None:
            # If we are at the end of the build queue, then add a default build
            self.add_next_default_build()
        else:
            # Build the current build target
            await self.create_build_target(current_build_target)


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
        saturated_extractors = self.bot.units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters > extr.ideal_harvesters)

        unsaturated_extractors = self.bot.units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters < extr.ideal_harvesters)

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

    async def manage_queens(self):
        queens = self.bot.units(const.QUEEN).idle
        townhalls = self.bot.townhalls

        if townhalls.exists:
            for queen in queens:
                if queen.energy > 25:
                    abilities = await self.bot.get_available_abilities(queen)

                    creep_tumors = self.bot.units({const.CREEPTUMOR, const.CREEPTUMORBURROWED})

                    if (not creep_tumors.exists or creep_tumors.amount == 5) and \
                            not self._recent_commands.contains(ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                                               self.bot.state.game_loop):
                        # Spawn creep tumor if we have none
                        if const.BUILD_CREEPTUMOR_QUEEN in abilities:
                            townhall = townhalls.closest_to(queen.position)
                            position = townhall.position.towards_with_random_angle(
                                self.bot.enemy_start_location, random.randint(9, 11),
                                max_difference=(math.pi / 2.2))

                            self._recent_commands.add(
                                ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                self.bot.state.game_loop, expiry=15)

                            self.bot.actions.append(queen(const.BUILD_CREEPTUMOR_QUEEN, position))

                    else:
                        # Inject larvae
                        if const.EFFECT_INJECTLARVA in abilities:
                            closest_townhall = townhalls.closest_to(queen.position)
                            self.bot.actions.append(queen(const.EFFECT_INJECTLARVA, closest_townhall))

            for townhall in townhalls:
                closest_queens = queens.closer_than(5, townhall)

                # Move all but the closest queen to a random townhall
                second_closest_queens = closest_queens[1:]
                for queen in second_closest_queens:
                    other_townhalls = self.bot.townhalls.filter(
                        lambda th: th.tag != townhall.tag)
                    if other_townhalls.exists:
                        self.bot.actions.append(queen.move(other_townhalls.random))

    async def manage_creep_tumors(self):
        creep_tumors = self.bot.units({const.CREEPTUMORBURROWED})

        for tumor in creep_tumors:
            abilities = await self.bot.get_available_abilities(tumor)
            if const.BUILD_CREEPTUMOR_TUMOR in abilities:
                position = tumor.position.towards_with_random_angle(
                    self.bot.enemy_start_location, random.randint(9, 11),
                    max_difference=(math.pi / 2.2))

                self.bot.actions.append(tumor(const.BUILD_CREEPTUMOR_TUMOR, position))


    async def run(self):
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

        # Flag for if we find an enemy proxy or rush
        self.enemy_proxy_found = False
        self.proxy_search_concluded = False

        # Tags of overlords with creep turned on
        self.overlord_tags_with_creep_turned_on = set()

    @property
    def scouting_overlord_tags(self):
        return {self.scouting_overlord_tag,
                self.proxy_scouting_overlord_tag,
                self.third_expansion_scouting_overlord_tag}

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
        overlords = self.bot.units(const.OVERLORD).filter(lambda o: o.tag not in self.scouting_overlord_tags)

        for overlord in overlords:
            other_overlords = overlords.filter(lambda o: o.tag != overlord.tag)

            if other_overlords.exists:
                closest_overlord = other_overlords.closest_to(overlord)

                distance = overlord.distance_to(closest_overlord)
                # 11 is overlord vision radius
                if 11*2.3 > distance:
                    away_from_other_overlord = overlord.position.towards(closest_overlord.position, -1)
                    self.bot.actions.append(overlord.move(away_from_other_overlord))

    async def proxy_scout_with_second_overlord(self):
        overlords = self.bot.units(const.OVERLORD)

        if self.proxy_scouting_overlord_tag is None:
            if overlords.exists and overlords.amount == 2:
                overlord = overlords.filter(lambda ov: ov.tag not in self.scouting_overlord_tags).first
                self.proxy_scouting_overlord_tag = overlord.tag

                expansion_location = await self.bot.get_next_expansion()

                overlord_mov_pos_1 = expansion_location.towards(self.bot.enemy_start_location, +10)
                overlord_mov_pos_2 = expansion_location.towards(self.bot.enemy_start_location, -3)

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
                    if enemy_structures.closer_than(90, self.bot.start_location).exists:
                        self.enemy_proxy_found = True
                        self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY)

                    # Report enemy rushes
                    enemy_units = self.bot.known_enemy_units.not_structure
                    if enemy_units.exists:
                        nearby_enemy_units = enemy_units.exclude_type(
                            const2.ENEMY_NON_ARMY).closer_than(90, self.bot.start_location)
                        enemy_workers = nearby_enemy_units.of_type(const2.WORKERS)
                        nearby_enemy_units = nearby_enemy_units - enemy_workers
                        if enemy_workers.exists and enemy_workers.amount > 3:
                            # Found enemy worker rush
                            self.enemy_proxy_found = True
                            self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH)
                        elif nearby_enemy_units.exists and nearby_enemy_units.amount > 1:
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
                    # Overlord has died :(  (Or become a beautiful Overseer :) )
                    self.proxy_scouting_overlord_tag = None

    async def scout_enemy_third_expansion_with_third_overlord(self):
        overlords = self.bot.units(const.OVERLORD)

        if self.third_expansion_scouting_overlord_tag is None:
            if overlords.exists and overlords.amount == 3:
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
        overlords = self.bot.units(const.OVERLORD)

        for overlord in overlords:
            if overlord.health_percentage != 1:
                nearby_enemy_units = self.bot.units.enemy.\
                    closer_than(10, overlord).filter(lambda unit: unit.can_attack_air)

                if nearby_enemy_units.exists:
                    nearby_enemy_unit = nearby_enemy_units.closest_to(overlord)
                    away_from_enemy = overlord.position.towards(nearby_enemy_unit, -1)
                    self.bot.actions.append(overlord.move(away_from_enemy))

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
                enemy_natural_expansion.position.towards(self.bot.start_location, +22)
            self.bot.actions.append(overlord.move(away_from_enemy_natural_expansion))

    async def do_initial_backout(self):
        await self.overlord_flee()

    async def do_suicide_dive(self):
        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            enemy_natural_expansion = self.bot.get_enemy_natural_expansion()
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

                if distance_to_expansion < 18:
                    # Take note of enemy defensive structures sited
                    enemy_defensive_structures_types = {const.PHOTONCANNON, const.SPINECRAWLER}
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
                if self.bot.known_enemy_structures.amount < 4:
                    await self.change_state(OverlordStates.SUICIDE_DIVE)

        elif self.state == OverlordStates.INITIAL_DIVE:
            enemy_structures = self.bot.known_enemy_structures
            overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
            if overlord:
                distance_to_enemy_start_location = overlord.distance_to(self.bot.enemy_start_location)
                if distance_to_enemy_start_location < 24:
                    # Take note of enemy defensive structures sited
                    enemy_defensive_structures_types = {const.PHOTONCANNON, const.SPINECRAWLER}
                    nearby_enemy_defensive_structures = enemy_structures.of_type(
                        enemy_defensive_structures_types).closer_than(15, overlord)
                    if nearby_enemy_defensive_structures.exists:
                        closest_enemy_defensive_structure = \
                            nearby_enemy_defensive_structures.closest_to(overlord)
                        self.publish(
                            Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                            value=closest_enemy_defensive_structure.position)

                if enemy_structures.closer_than(11, overlord).exists:
                    self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                    await self.change_state(OverlordStates.INITIAL_BACKOUT)

                    enemy_townhalls = enemy_structures.of_type(const2.TOWNHALLS)
                    if enemy_townhalls.exists:
                        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()
                        if enemy_townhalls.closer_than(4, enemy_natural_expansion):
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

        await self.overlord_dispersal()
        await self.turn_on_generate_creep()
        await self.proxy_scout_with_second_overlord()
        await self.scout_enemy_third_expansion_with_third_overlord()


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
            ForcesStates.DEFENDING: self.do_defending,
            ForcesStates.MOVING_TO_ATTACK: self.do_moving_to_attack,
            ForcesStates.ATTACKING: self.do_attacking,
            ForcesStates.SEARCHING: self.do_searching,
        }

        # Army value needed to do an attack. Changes with the current build stage.
        self.army_value_to_attack = 50

        # Map of functions to do when entering the state
        self.state_start_map = {
            ForcesStates.ATTACKING: self.start_attacking,
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
            ForcesStates.DEFENDING: self.stop_defending,
        }
        self._recent_commands = ExpiringList()

        # Set of worker ids of workers defending an attack.
        self.workers_defending = set()

        # Subscribe to messages
        self.subscribe(Messages.NEW_BUILD_STAGE)
        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)

    def get_army_value_to_attack(self, build_stage):
        """Given a build stage, returns the army value needed to begin an attack"""
        return {
            BuildStages.OPENING: 100000,  #  Don't attack
            BuildStages.EARLY_GAME: 6,  #  Only attack if we banked up some units early on
            BuildStages.MID_GAME: 50,  #  Attack when a sizeable army is gained
            BuildStages.LATE_GAME: 70,  #  Attack when a sizeable army is gained
        }[build_stage]

    def get_nearby_to_target(self):
        """
        Gets a point nearby the target.
        The point is 2/3rds the distance between our starting location and the target.
        Uses midpoint formula(math), edited slightly to get closer than midpoint.
        """

        enemy_structures = self.bot.known_enemy_structures

        # Get target to attack towards
        if enemy_structures.exists:
            target = enemy_structures.closest_to(self.bot.start_location).position
        else:
            target = self.bot.enemy_start_location.position

        return target.towards(self.bot.start_location.position, +35)
        # return (self.bot.start_location.position + target) / 1.5

    async def do_housekeeping(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

        townhalls = self.bot.townhalls

        # Ensure each town hall has some army nearby
        # Do it at max every 10 seconds
        for townhall in townhalls:
            nearby_army = army.closer_than(12, townhall.position)

            # A majority of the standing army should be at town halls, divided evenly.
            number_of_units_to_townhall = round(len(army) / len(townhalls) / 1.2)
            if len(nearby_army) < number_of_units_to_townhall:
                far_army = army.further_than(12, townhall.position)
                if far_army.exists:
                    self.bot.actions.append(far_army.random.attack(townhall.position))

    async def do_defending(self):
        """
        Defend townhalls from nearby enemies
        """

        for th in self.bot.townhalls:
            enemies_nearby = self.bot.known_enemy_units.closer_than(15, th.position)

            if enemies_nearby.exists:
                # Workers attack enemy
                ground_enemies = enemies_nearby.not_flying
                workers = self.bot.workers.closer_than(15, enemies_nearby.random.position)
                if workers.exists and ground_enemies.exists and \
                        workers.amount > ground_enemies.amount:
                    for worker in workers:
                        if len(self.workers_defending) <= ground_enemies.amount:
                            if worker.tag not in self.workers_defending:
                                target = ground_enemies.random
                                self.bot.actions.append(worker.attack(target.position))
                                self.workers_defending.add(worker.tag)

                # Have queens defend
                queens = self.bot.units(const.QUEEN)
                if queens.exists:
                    if enemies_nearby.amount > 2:
                        defending_queens = queens
                    else:
                        defending_queens = [queens.closest_to(
                            enemies_nearby.random.position)]

                    for queen in defending_queens:
                        target = enemies_nearby.closest_to(queen)
                        if target.distance_to(queen) < queen.ground_range:
                            # Target
                            self.bot.actions.append(queen.attack(target))
                        else:
                            # Position
                            self.bot.actions.append(queen.attack(target.position))

                # Have army defend
                nearby_army = self.bot.units().filter(
                    lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).\
                    closer_than(65, th.position)

                for unit in nearby_army:
                    target = enemies_nearby.closest_to(unit)

                    if unit.can_attack_ground and not target.is_flying or \
                            unit.can_attack_air and target.is_flying:
                        self.bot.actions.append(unit.attack(target))

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

    async def do_moving_to_attack(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

        if not army.exists:
            return

        # Get target to attack towards
        nearby_target = self.get_nearby_to_target()

        # Search for another spot to move to
        # if not self.bot.in_pathing_grid(nearby_target):
        nearby_target = self.bot.find_nearby_pathable_point(nearby_target)

        for unit in army:
            self.bot.actions.append(unit.attack(nearby_target))

    async def start_attacking(self):
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

    async def do_attacking(self):
        # Do main force attacking
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).\
            exclude_type(const2.ZERG_HARASS_UNITS)

        if not army.exists:
            return

        target = self.bot.known_enemy_structures.random_or(
            self.bot.enemy_start_location).position

        for unit in army:
            self.bot.actions.append(unit.attack(target))

    async def do_searching(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS).idle

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

            if message in {Messages.NEW_BUILD_STAGE}:
                self.ack(message)
                new_army_value_to_attack = self.get_army_value_to_attack(val)
                self.army_value_to_attack = new_army_value_to_attack
                print("{}: New army value to attack with: {}".format(
                    self.name, new_army_value_to_attack))

        # HOUSEKEEPING
        if self.state == ForcesStates.HOUSEKEEPING:

            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            if army.exists:
                # Value of the army
                army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

                # Average army health percentage
                army_health_average = sum([unit.health_percentage for unit in army]) / army.amount

                if army_value > self.army_value_to_attack and army_health_average > 0.85:
                    return await self.change_state(ForcesStates.MOVING_TO_ATTACK)

        # DEFENDING
        elif self.state == ForcesStates.DEFENDING:
            # Loop through all townhalls. If enemies are near any of them, don't change state.
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    15, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby.exists:
                    # Enemies found, don't change state.
                    break
            else:
                return await self.change_state(self.previous_state)

        # MOVING_TO_ATTACK
        elif self.state == ForcesStates.MOVING_TO_ATTACK:
            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            if army.exists:
                # Value of the army
                army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

                # Average army health percentage
                army_health_average = sum([unit.health_percentage for unit in army]) / army.amount

                if army_value < self.army_value_to_attack or army_health_average < 0.8:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

                # Start attacking when army has amassed
                nearby_target = self.get_nearby_to_target()
                if army.center.distance_to(nearby_target) < 7:
                    return await self.change_state(ForcesStates.ATTACKING)

        # ATTACKING
        elif self.state == ForcesStates.ATTACKING:
            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            # Value of the army
            army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

            if army_value < self.army_value_to_attack:
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

            units_at_enemy_location = self.bot.units().closer_than(
                6, self.bot.enemy_start_location)

            if units_at_enemy_location.exists:
                self.publish(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)

        # Switching to DEFENDING from any other state
        if self.state != ForcesStates.DEFENDING:
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    15, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby.exists:
                    return await self.change_state(ForcesStates.DEFENDING)


class MicroManager(StatefulManager):
    """
    Manager for microing army units
    """

    name = 'Micro Manager'

    def __init__(self, bot):
        super(MicroManager, self).__init__(bot)

    async def manage_ravagers(self):
        ravagers = self.bot.units(const.RAVAGER)

        bile_priorities = {
            const.OVERLORD, const.MEDIVAC, const.SIEGETANKSIEGED,
            const.PHOTONCANNON, const.SPINECRAWLER, const.PYLON, const.MISSILETURRET,
        }

        for ravager in ravagers:
            # Perform bile attacks
            # Bile range is 9
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(9, ravager)
            if nearby_enemy_units.exists:
                nearby_enemy_priorities = nearby_enemy_units.of_type(bile_priorities)

                # Prefer targeting our bile_priorities
                nearby_enemy_units = nearby_enemy_priorities if nearby_enemy_priorities.exists else nearby_enemy_units

                for enemy_unit in nearby_enemy_units.sorted(
                        lambda unit: ravager.distance_to(unit), reverse=True):
                    our_closest_unit_to_enemy = self.bot.units().closest_to(enemy_unit)
                    if our_closest_unit_to_enemy.distance_to(enemy_unit) > 1:
                        self.bot.actions.append(ravager(const.EFFECT_CORROSIVEBILE, enemy_unit.position))
                        break

    async def manage_mutalisks(self):
        mutalisks = self.bot.units(const.MUTALISK)

        attack_priorities = {const.QUEEN}

        for mutalisk in mutalisks:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(11, mutalisk)
            if nearby_enemy_units.exists:
                # Only begin concentrated targeting near enemy town halls
                if nearby_enemy_units.of_type(const2.TOWNHALLS).exists:
                    nearby_enemy_workers = nearby_enemy_units.of_type(const2.WORKERS)
                    nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priorities)
                    nearby_enemy_can_attack_air = nearby_enemy_units.filter(lambda u: u.can_attack_air)

                    # TOO MANY BADDIES. GET OUT OF DODGE
                    if nearby_enemy_can_attack_air.amount > 1:
                        towards_start_location = mutalisk.position.towards(self.bot.start_location, 80)
                        self.bot.actions.append(mutalisk.move(towards_start_location))

                    # Prefer targeting our priorities
                    if nearby_enemy_workers.exists:
                        nearby_enemy_units = nearby_enemy_workers
                    elif nearby_enemy_priorities.exists:
                        nearby_enemy_units = nearby_enemy_priorities

                    nearby_enemy_unit = nearby_enemy_units.closest_to(mutalisk)
                    self.bot.actions.append(mutalisk.attack(nearby_enemy_unit))

    async def manage_spine_crawlers(self):
        rooted_spine_crawlers = self.bot.units(const.SPINECRAWLER)
        uprooted_spine_crawlers = self.bot.units(const.SPINECRAWLERUPROOTED)
        spine_crawlers = rooted_spine_crawlers | uprooted_spine_crawlers
        townhalls = self.bot.townhalls.ready

        if spine_crawlers.exists:
            if townhalls.exists:
                townhall = townhalls.closest_to(self.bot.enemy_start_location)
                nearby_spine_crawlers = spine_crawlers.closer_than(22, townhall)

                # Unroot spine crawlers that are far away from the front expansions
                if not nearby_spine_crawlers.exists or (
                        nearby_spine_crawlers.exists and nearby_spine_crawlers.amount < spine_crawlers.amount / 2):

                    for sc in rooted_spine_crawlers.idle:
                        self.bot.actions.append(sc(const.AbilityId.SPINECRAWLERUPROOT_SPINECRAWLERUPROOT))

                # Root unrooted spine crawlers near the front expansions
                for sc in uprooted_spine_crawlers.idle:
                    near_townhall = townhall.position.towards_with_random_angle(
                        self.bot.enemy_start_location, 10, max_difference=(math.pi / 3.0))
                    position = await self.bot.find_placement(
                        const.SPINECRAWLER, near_townhall, max_distance=20)

                    self.bot.actions.append(
                        sc(const.AbilityId.SPINECRAWLERROOT_SPINECRAWLERROOT, position))

    async def run(self):
        await self.manage_ravagers()
        await self.manage_mutalisks()
        await self.manage_spine_crawlers()


class LambdaBot(sc2.BotAI):
    def __init__(self):
        self.intel_manager = None
        self.build_manager = None
        self.resource_manager = None
        self.overlord_manager = None
        self.force_manager = None
        self.micro_manager = None

        self.iteration = 0

        # "Do" actions to run
        self.actions = []

        # Message subscriptions
        self._message_subscriptions: Dict[const2.Messages, Manager] = defaultdict(list)

        # Global Intel
        self.enemy_start_location = None
        self.not_enemy_start_locations = None

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
                self, starting_build=Builds.EARLY_GAME_DEFAULT_OPENER)
            self.resource_manager = ResourceManager(self)
            self.overlord_manager = OverlordManager(self)
            self.force_manager = ForceManager(self)
            self.micro_manager = MicroManager(self)

            await self.chat_send("λ LΛMBDANAUT λ - {}".format(VERSION))

        await self.intel_manager.run()  # Run before all other managers

        await self.build_manager.run()
        await self.resource_manager.run()
        await self.force_manager.run()
        await self.micro_manager.run()

        # Do this more rarely. Less important. Start on third iteration.
        if iteration % 15 == 3:
            await self.overlord_manager.run()

        # "Do" actions
        await self.do_actions(self.actions)

        # Reset actions
        self.actions = []

    async def on_unit_created(self, unit):

        # Always allow banelings to attack structures
        if unit.type_id == const.BANELING:
            self.actions.append(unit(const.BEHAVIOR_BUILDINGATTACKON))

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

    def find_nearby_pathable_point(self, near: sc2.position.Point2) -> Union[None, sc2.position.Point2]:
        placement_step = 2
        for distance in range(2, 30, 2):

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


