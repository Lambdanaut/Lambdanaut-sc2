from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Union

import sc2
import sc2.constants as const

import lambdanaut.builds as builds
import lambdanaut.const2 as const2

from lambdanaut.const2 import Messages, BuildManagerCommands, ForcesStates, OverlordStates
from lambdanaut.expiringlist import ExpiringList


VERSION = '2.0'
BUILD = builds.TWO_BASE_LING_RUSH


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
        print('{}: Message published: {}'.format(self.name, message_type.name))
        return self.bot.publish(self, message_type, value)

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

    This is the only class with permission to directly edit variables in
    the Lambdanaut class.
    """

    name = 'Intel Manager'

    def __init__(self, bot):
        super(IntelManager, self).__init__(bot)

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
                    print('{}: bug while finding a new start location'.format(self.name, ))
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


    async def run(self):
        await self.read_messages()


class BuildManager(Manager):

    name = 'Build Manager'

    def __init__(self, bot, build_order=None):
        super(BuildManager, self).__init__(bot)

        self.build_queue = []

        # Dict with ttl so that we know what build commands were recently issued
        # For avoiding things like building two extractors when we needed 1
        # [EXTRACTOR, HATCHERY, etc. etc..]
        self._recent_build_orders = ExpiringList()

        # Recent commands issued. Uses constants defined in const2.py
        self._recent_commands = ExpiringList()

        self.build_target = None
        self.last_build_target = None

        if build_order is not None:
            self.load_build_order(build_order)

    def can_afford(self, unit):
        """Returns boolean indicating if the player has enough minerals,
        vespene, and supply to build the unit"""

        can_afford = self.bot.can_afford(unit)
        return can_afford.can_afford_minerals and \
               can_afford.can_afford_vespene and \
               can_afford.have_enough_supply

    def load_build_order(self, build_order: list):
        self.build_queue = build_order

    def current_build_target(self):
        """
        Goes through the build order one by one counting up all the units and
        stopping once we hit a unit we don't yet have

        :returns Unit Type or None
        """

        # Count of existing units {unit.type_id: count}
        existing_unit_counts = Counter(map(lambda unit: unit.type_id, self.bot.units))

        # Units still being built in eggs (to be added to existing units counter)
        units_in_eggs = Counter([get_training_unit(egg)
                                 for egg in self.bot.units(const.EGG)])

        # Units being trained in hatcheries (to be added to existing units counter)
        units_being_trained = Counter([get_training_unit(hatchery)
                                       for hatchery in self.bot.units(const.HATCHERY)])

        # Baneling Eggs count as banelings
        baneling_eggs = Counter({const.BANELING: len(self.bot.units(const.EGG))})

        # Overseer cocoons count as Overseers
        overseer_cocoons = Counter({const.OVERSEER: len(self.bot.units(const.OVERLORDCOCOON))})

        # Units recently ordered to be built.
        recent_build_orders = Counter(self._recent_build_orders.items(self.bot.iteration))

        # Count of existing upgrades
        existing_upgrades = Counter(self.bot.state.upgrades)

        existing_unit_counts += units_in_eggs
        existing_unit_counts += units_being_trained
        existing_unit_counts += baneling_eggs
        existing_unit_counts += recent_build_orders
        existing_unit_counts += existing_upgrades

        # Set the number of hatcheries to be the number of town halls
        # (We want to count Lairs and Hives as hatcheries too. They're all expansions)
        existing_unit_counts[const.HATCHERY] = len(self.bot.townhalls)

        # Count of units in build order up till this point {unit.type_id: count}
        build_order_counts = Counter()

        for unit in self.build_queue:
            build_order_counts[unit] += 1

            if existing_unit_counts[unit] < build_order_counts[unit]:
                # Found build target
                self.last_build_target = self.build_target
                self.build_target = unit

                return unit

        return None

    async def create_build_target(self):
        """
        Main function that issues commands to build next build order target
        """

        if self.last_build_target != self.build_target:
            print("Build target: {}".format(self.build_target))

        build_target = self.current_build_target()

        # Check type of unit we're building to determine how to build

        if build_target == const.HATCHERY:
            expansion_location = await self.bot.get_next_expansion()

            if self.can_afford(build_target):
                await self.bot.expand_now()

                # Keep from issuing another expand command for 30 seconds
                self._recent_build_orders.add(
                    build_target, iteration=self.bot.iteration, expiry=30)

            # Move drone to expansion location before construction
            elif self.bot.state.common.minerals > 200 and \
                    not self._recent_commands.contains(
                        BuildManagerCommands.EXPAND_MOVE, self.bot.iteration):
                if expansion_location:
                    nearest_drone = self.bot.units(const.DRONE).closest_to(expansion_location)
                    # Only move the drone to the expansion location if it's far away
                    # To keep from constantly issuing move commands
                    if nearest_drone.distance_to(expansion_location) > 9:
                        self.bot.actions.append(nearest_drone.move(expansion_location))

                        # Keep from issuing another expand move command
                        self._recent_commands.add(
                            BuildManagerCommands.EXPAND_MOVE, self.bot.iteration, expiry=10)

        elif build_target == const.LAIR:
            # Get a hatchery
            hatcheries = self.bot.units(const.HATCHERY)

            # Train the unit
            if self.can_afford(build_target) and hatcheries.exists:
                self.bot.actions.append(hatcheries.random.build(build_target))

        elif build_target == const.EXTRACTOR:
            if self.can_afford(build_target):
                townhall = self.bot.townhalls.filter(lambda th: th.is_ready).first
                geyser = self.bot.state.vespene_geyser.closest_to(townhall)
                drone = self.bot.workers.closest_to(geyser)

                if self.can_afford(build_target):
                    err = self.bot.actions.append(drone.build(build_target, geyser))

                    # Add structure order to recent build orders
                    if not err:
                        self._recent_build_orders.add(build_target, iteration=self.bot.iteration, expiry=10)

        elif build_target == const.QUEEN:

            idle_hatcheries = self.bot.units(const.HATCHERY).idle

            if self.can_afford(build_target) and idle_hatcheries.exists:
                self.bot.actions.append(
                    idle_hatcheries.random.train(build_target))

        elif build_target in const2.ZERG_STRUCTURES_FROM_DRONES:
            hatchery = self.bot.units(const.HATCHERY).ready.first

            if self.can_afford(build_target):
                err = await self.bot.build(build_target, near=hatchery)

                # Add structure order to recent build orders
                if not err:
                    self._recent_build_orders.add(build_target, iteration=self.bot.iteration, expiry=10)

        elif build_target in const2.ZERG_UNITS_FROM_LARVAE:
            # Get a larvae
            larvae = self.bot.units(const.LARVA)

            # Train the unit
            if self.can_afford(build_target) and larvae.exists:
                self.bot.actions.append(larvae.random.train(build_target))

        elif build_target == const.BANELING:
            # Get a zergling
            zerglings = self.bot.units(const.ZERGLING)

            # Train the unit
            if self.can_afford(build_target) and zerglings.exists:
                self.bot.actions.append(zerglings.random.train(build_target))

        elif build_target == const.OVERSEER:
            # Get an overlord
            overlords = self.bot.units(const.OVERLORD)

            # Train the unit
            if self.can_afford(build_target) and overlords.exists:
                self.bot.actions.append(overlords.random.train(build_target))

        # Upgrades below
        elif build_target == const.ZERGLINGMOVEMENTSPEED:
            sp = self.bot.units(const.SPAWNINGPOOL).ready
            if self.can_afford(build_target) and sp.exists:
                err = self.bot.actions.append(sp.first(const.RESEARCH_ZERGLINGMETABOLICBOOST))

                if not err:
                    self._recent_build_orders.add(build_target, iteration=self.bot.iteration, expiry=200)

        elif build_target == const.CENTRIFICALHOOKS:
            bn = self.bot.units(const.BANELINGNEST).ready
            if self.can_afford(build_target) and bn.exists:
                err = await self.bot.do(bn.first(const.RESEARCH_CENTRIFUGALHOOKS))

                if not err:
                    self._recent_build_orders.add(build_target, iteration=self.bot.iteration, expiry=200)


    async def run(self):
        return await self.create_build_target()


class ResourceManager(Manager):
    """
    Class for handling resource management. Involves:

    * Worker harvester management
    * Queen injection
    * Queen creep spread
    """

    name = 'Resource Manager'

    def __init__(self, bot):
        super(ResourceManager, self).__init__(bot)

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
            worker = mineral_workers.closest_to(saturated_townhall)
            unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
            mineral = self.bot.state.mineral_field.closest_to(unsaturated_townhall)

            self.bot.actions.append(worker.gather(mineral, queue=True))

    async def manage_minerals(self):
        await self.manage_mineral_saturation()

        # Move idle workers to mining
        for worker in self.bot.workers.idle:
            townhall = self.bot.townhalls.closest_to(worker.position)
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

        for queen in queens:
            if queen.energy > 25:
                abilities = await self.bot.get_available_abilities(queen)
                if const.AbilityId.EFFECT_INJECTLARVA in abilities:
                    townhall = self.bot.townhalls.closest_to(queen.position)
                    if townhall:
                        self.bot.actions.append(queen(const.EFFECT_INJECTLARVA, townhall))

        for townhall in self.bot.townhalls:
            closest_queens = queens.closer_than(5, townhall)

            # Move all but the closest queen to a random townhall
            second_closest_queens = closest_queens[1:]
            for queen in second_closest_queens:
                other_townhalls = self.bot.townhalls.filter(
                    lambda th: th.tag != townhall.tag)
                if other_townhalls.exists:
                    self.bot.actions.append(queen.move(other_townhalls.random))

    async def run(self):
        await self.manage_resources()
        await self.manage_queens()


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

        # Set of overlords used for scouting
        self.scouting_overlords = {self.bot.units(const.OVERLORD).first.tag}

    async def overlord_dispersal(self):
        """
        Disperse Overlords evenly around base
        """
        overlords = self.bot.units(const.OVERLORD)

        for overlord in overlords:
            other_overlords = overlords.filter(lambda o: o.tag != overlord.tag)

            if other_overlords.exists:
                closest_overlord = other_overlords.closest_to(overlord)

                distance = overlord.distance_to(closest_overlord)
                # 11 is overlord vision radius
                if 11*2.3 > distance:
                    away_from_other_overlord = overlord.position.towards(closest_overlord.position, -1)
                    self.bot.actions.append(overlord.move(away_from_other_overlord))

    async def do_initial(self):
        """
        We haven't seen any enemy structures yet
        Move towards enemy's natural expansion
        """
        await self.overlord_dispersal()

        # Early game scouting

        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        for overlord_tag in self.scouting_overlords:
            overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
            if overlord:
                # Move towards natural expansion
                self.bot.actions.append(overlord.move(enemy_natural_expansion))

    async def start_initial_backout(self):
        """
        We've seen enemy structures
        Retreat from their natural expansion
        """

        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        for overlord_tag in self.scouting_overlords:
            overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
            if overlord:
                # Move in closer towards main
                away_from_enemy_natural_expansion = \
                    enemy_natural_expansion.position.towards(self.bot.start_location, +22)
                self.bot.actions.append(overlord.move(away_from_enemy_natural_expansion))

    async def do_initial_backout(self):
        await self.overlord_dispersal()

    async def start_suicide_dive(self):

        for overlord_tag in self.scouting_overlords:
            overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
            if overlord:
                self.bot.actions.append(
                    overlord.move(self.bot.enemy_start_location.position))

    async def do_suicide_dive(self):
        await self.overlord_dispersal()

    async def start_initial_dive(self):
        for overlord_tag in self.scouting_overlords:
            overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
            if overlord:
                self.bot.actions.append(
                    overlord.move(self.bot.enemy_start_location.position))

    async def do_initial_dive(self):
        await self.overlord_dispersal()

    async def determine_state_change(self):
        if self.state == OverlordStates.INITIAL:
            enemy_structures = self.bot.known_enemy_structures
            enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

            for overlord_tag in self.scouting_overlords:
                overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
                if overlord:
                    if overlord.distance_to(enemy_natural_expansion) < 11:
                        if enemy_structures.closer_than(12, overlord).exists:
                            self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                            return await self.change_state(OverlordStates.INITIAL_BACKOUT)
                        else:
                            return await self.change_state(OverlordStates.INITIAL_DIVE)

        elif self.state == OverlordStates.INITIAL_BACKOUT:
            pass

        elif self.state == OverlordStates.INITIAL_DIVE:
            enemy_structures = self.bot.known_enemy_structures
            for overlord_tag in self.scouting_overlords:
                overlord = self.bot.units(const.OVERLORD).find_by_tag(overlord_tag)
                if overlord:
                    if enemy_structures.closer_than(12, overlord).exists:
                        self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                        return await self.change_state(OverlordStates.INITIAL_BACKOUT)
                    elif overlord.distance_to(self.bot.enemy_start_location) < 10:
                        self.publish(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
                        return await self.change_state(OverlordStates.INITIAL_BACKOUT)

        elif self.state == OverlordStates.SUICIDE_DIVE:
            pass


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

        # Map of functions to do when entering the state
        self.state_start_map = {
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
            ForcesStates.DEFENDING: self.stop_defending,
        }
        self._recent_commands = ExpiringList()

        # Set of worker ids of workers defending an attack.
        self.workers_defending = set()

        # Subscribe to messages
        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)

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

        return target.towards(self.bot.start_location.position, +30)
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
                if workers.exists and enemies_nearby.exists and \
                        workers.amount > enemies_nearby.amount:
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
                    closer_than(50, th.position)

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
        if not self.bot.in_pathing_grid(nearby_target):
            nearby_target = self.bot.find_nearby_pathable_point(nearby_target)

        for unit in army:
            self.bot.actions.append(unit.attack(nearby_target))

    async def do_attacking(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

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
            if message in {Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION}:
                if self.state != ForcesStates.DEFENDING:
                    self.ack(message)
                    return await self.change_state(ForcesStates.SEARCHING)

        # HOUSEKEEPING
        if self.state == ForcesStates.HOUSEKEEPING:

            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            # Value of the army
            army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

            if army_value > 100:
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

            # Value of the army
            army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

            if army_value < 100:
                return await self.change_state(ForcesStates.HOUSEKEEPING)

            nearby_target = self.get_nearby_to_target()
            if army.center.distance_to(nearby_target) < 7:
                return await self.change_state(ForcesStates.ATTACKING)

        # ATTACKING
        elif self.state == ForcesStates.ATTACKING:
            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            # Value of the army
            army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

            if army_value < 100:
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


class LambdaBot(sc2.BotAI):
    def __init__(self):
        self.build_manager = None
        self.resource_manager = None
        self.overlord_manager = None
        self.force_manager = None
        self.intel_manager = None

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
            # Setup Global Intel variables
            self.enemy_start_location = self.enemy_start_locations[0]
            self.not_enemy_start_locations = {self.start_location}

            # Load up managers
            self.intel_manager = IntelManager(self)
            self.build_manager = BuildManager(self, build_order=BUILD)
            self.resource_manager = ResourceManager(self)
            self.overlord_manager = OverlordManager(self)
            self.force_manager = ForceManager(self)

            await self.chat_send("Lambdanaut v{}".format(VERSION))

        await self.intel_manager.run()  # Run before all other managers

        await self.build_manager.run()
        await self.resource_manager.run()
        await self.force_manager.run()

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

    def get_enemy_expansion_positions(self) -> List[sc2.position.Point2]:
        """Returns enemy expansion positions in order from their nearest to furthest"""

        enemy_start_location = self.enemy_start_location.position

        expansions = self.expansion_locations.keys()
        enemy_expansion_position = enemy_start_location.sort_by_distance(expansions)

        return enemy_expansion_position

    def get_enemy_natural_expansion(self) -> Union[None, sc2.position.Point2]:
        try:
            return self.get_enemy_expansion_positions()[1]
        except IndexError:
            return None

    def find_nearby_pathable_point(self, near: sc2.position.Point2) -> Union[None, sc2.position.Point2]:
        placement_step = 2
        for distance in range(2, 20, 2):

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


