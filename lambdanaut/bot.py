from collections import Counter

import sc2
import sc2.constants as const

import lambdanaut.builds as builds
import lambdanaut.const2 as const2

from lambdanaut.const2 import BuildManagerCommands, ForcesStates, ForceCommands
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
    async def run(self):
        raise NotImplementedError;


class BuildManager(Manager):
    def __init__(self, bot, build_order=None):
        self.bot = bot
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

                # Keep from issuing another expand command for 10 seconds
                self._recent_build_orders.add(
                    build_target, iteration=self.bot.iteration, expiry=10)

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

    def __init__(self, bot):
        self.bot = bot

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


    async def run(self):
        await self.manage_resources()
        await self.manage_queens()


class ForceManager(Manager):
    """
    State-machine for controlling forces

    States need a few things to work

    * They need a `do` function in self.state_map for them to do something each frame.
    * They need conditions defined in self.determine_state_change to switch into that state
    * Optionally they can also have a `stop` function in self.state_stop_map which runs
      when that state is exited.
    """

    def __init__(self, bot):
        self.bot = bot

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
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
            ForcesStates.DEFENDING: self.stop_defending,
        }
        self._recent_commands = ExpiringList()

        # Set of worker ids of workers defending an attack.
        self.workers_defending = set()

    async def do_housekeeping(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

        townhalls = self.bot.townhalls

        # Ensure each town hall has some army nearby
        # Do it at max every 10 seconds
        for townhall in townhalls:
            nearby_army = army.closer_than(12, townhall.position)

            # At least half of the standing army should be at town halls, divided evenly.
            number_of_units_to_townhall = round(len(army) / len(townhalls) / 2)
            if len(nearby_army) < number_of_units_to_townhall:
                far_army = army.further_than(12, townhall.position)
                if far_army.exists:
                    self.bot.actions.append(far_army.random.attack(townhall.position))

    async def do_defending(self):
        """
        Defend townhalls from nearby enemies
        Not dependent on state. Always consider defense if attacked.
        """

        for th in self.bot.townhalls:
            enemies_nearby = self.bot.known_enemy_units.closer_than(15, th.position)

            if enemies_nearby.exists:
                # Workers attack enemy
                ground_enemies = enemies_nearby.not_flying
                workers = self.bot.workers.closer_than(15, enemies_nearby.random.position)
                if workers.amount > enemies_nearby.amount:
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
                army = self.bot.units().filter(
                    lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

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
        pass

    async def do_attacking(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

        target = self.bot.known_enemy_structures.random_or(
            self.bot.enemy_start_locations[0]).position

        for unit in army:
            self.bot.actions.append(unit.attack(target))

    async def determine_state_change(self):
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
            return await self.change_state(ForcesStates.ATTACKING)

        # ATTACKING
        elif self.state == ForcesStates.ATTACKING:
            army = self.bot.units().filter(
                lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

            # Value of the army
            army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

            if army_value < 100:
                return await self.change_state(ForcesStates.HOUSEKEEPING)

        # Switching to DEFENDING from any other state
        if self.state != ForcesStates.DEFENDING:
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    15, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby.exists:
                    return await self.change_state(ForcesStates.DEFENDING)

    async def change_state(self, new_state):
        """
        Changes the state and runs a stop function if specified
        in self.state_stop_map
        """

        print('STATE CHANGED TO: {}'.format(new_state.name))

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
        await self.state_map[self.state]()

    async def run(self):
        await self.determine_state_change()
        await self.run_state()


class LambdaBot(sc2.BotAI):
    def __init__(self):
        self.build_manager = BuildManager(self, build_order=BUILD)

        self.resource_manager = ResourceManager(self)

        self.force_manager = ForceManager(self)

        self.iteration = 0

        # "Do" actions to run
        self.actions = []

    async def on_step(self, iteration):

        self.iteration = iteration

        if iteration == 0:
            await self.chat_send("Lambdanaut v{}".format(VERSION))

        await self.build_manager.run()
        await self.resource_manager.run()
        await self.force_manager.run()

        # "Do" actions
        await self.do_actions(self.actions)

        # Reset actions
        self.actions = []
