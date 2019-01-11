from collections import Counter
from expiringdict import ExpiringDict

import sc2
import sc2.constants as const

import lambdanaut.builds as builds
import lambdanaut.const2 as const2


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


class BuildManager(object):
    def __init__(self, bot):
        self.bot = bot
        self.build_queue = []

        # Dict with ttl so that we know what build commands were recently issued
        # For avoiding things like building two extractors when we needed 1
        # {EXTRACTOR: 1}
        self._recent_build_orders_10_second = ExpiringDict(max_age_seconds=10, max_len=100)
        self._recent_build_orders_200_second = ExpiringDict(max_age_seconds=200, max_len=100)

        # Recent commands issued. Uses constants defined in const2.py
        self._recent_commands_10_second = ExpiringDict(max_age_seconds=10, max_len=100)

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

        # Units recently ordered to be built. This is a private counter of items
        recent_build_orders1 = Counter(dict(self._recent_build_orders_10_second.items()))
        recent_build_orders2 = Counter(dict(self._recent_build_orders_200_second.items()))

        # Count of existing upgrades
        existing_upgrades = Counter(self.bot.state.upgrades)

        existing_unit_counts += units_in_eggs
        existing_unit_counts += units_being_trained
        existing_unit_counts += baneling_eggs
        existing_unit_counts += recent_build_orders1
        existing_unit_counts += recent_build_orders2
        existing_unit_counts += existing_upgrades

        # Set the number of hatcheries to be the number of town halls
        # (We want to count Lairs and Hives as hatcheries too. They're all expansions)
        existing_unit_counts[const.HATCHERY] = len(self.bot.townhalls)

        # Count of units in build order up till this point {unit.type_id: count}
        build_order_counts = Counter()

        for unit in self.build_queue:
            build_order_counts[unit] += 1

            if existing_unit_counts[unit] < build_order_counts[unit]:
                return unit

        return None

    async def create_build_target(self):
        """
        Main function that issues commands to build next build order target
        """

        build_target = self.current_build_target()

        print("Build target: {}".format(build_target))

        # Check type of unit we're building to determine how to build

        if build_target == const.HATCHERY:
            expansion_location = await self.bot.get_next_expansion()

            if self.can_afford(build_target):
                await self.bot.expand_now()

                # Keep from issuing another expand command for 10 seconds
                self._recent_build_orders_10_second[build_target] = 1

            # Move drone to expansion location before construction
            elif self.bot.state.common.minerals > 200 and \
                    const2.RECENT_EXPAND_MOVE_COMMAND not in self._recent_commands_10_second:
                if expansion_location:
                    nearest_drone = self.bot.units(const.DRONE).closest_to(expansion_location)
                    # Only move the drone to the expansion location if it's far away
                    # To keep from constantly issuing move commands
                    if nearest_drone.distance_to(expansion_location) > 9:
                        await self.bot.do(nearest_drone.move(expansion_location))

                        # Keep from issuing another expand move command
                        self._recent_commands_10_second[const2.RECENT_EXPAND_MOVE_COMMAND] = 1

        elif build_target == const.LAIR:
            # Get a hatchery
            hatcheries = self.bot.units(const.HATCHERY)

            # Train the unit
            if self.can_afford(build_target) and hatcheries.exists:
                await self.bot.do(hatcheries.random.build(build_target))

        elif build_target == const.EXTRACTOR:
            if self.can_afford(build_target):
                townhall = self.bot.townhalls.filter(lambda th: th.is_ready).first
                geyser = self.bot.state.vespene_geyser.closest_to(townhall)
                drone = self.bot.workers.closest_to(geyser)

                if self.can_afford(build_target):
                    err = await self.bot.do(drone.build(build_target, geyser))

                    # Add structure order to recent build orders
                    if not err:
                        self._recent_build_orders_10_second[build_target] = 1

        elif build_target == const.QUEEN:

            idle_hatcheries = self.bot.units(const.HATCHERY).idle

            if self.can_afford(build_target) and idle_hatcheries.exists:
                await self.bot.do(idle_hatcheries.random.train(build_target))

        elif build_target in const2.ZERG_STRUCTURES_FROM_DRONES:
            hatchery = self.bot.units(const.HATCHERY).ready.first

            if self.can_afford(build_target):
                err = await self.bot.build(build_target, near=hatchery)

                # Add structure order to recent build orders
                if not err:
                    self._recent_build_orders_10_second[build_target] = 1

        elif build_target in const2.ZERG_UNITS_FROM_LARVAE:
            # Get a larvae
            larvae = self.bot.units(const.LARVA)

            # Train the unit
            if self.can_afford(build_target) and larvae.exists:
                await self.bot.do(larvae.random.train(build_target))

        elif build_target == const.BANELING:
            # Get a zergling
            zerglings = self.bot.units(const.ZERGLING)

            # Train the unit
            if self.can_afford(build_target) and zerglings.exists:
                await self.bot.do(zerglings.random.train(build_target))

        # Upgrades below
        elif build_target == const.ZERGLINGMOVEMENTSPEED:
            sp = self.bot.units(const.SPAWNINGPOOL).ready
            if self.can_afford(build_target) and sp.exists:
                err = await self.bot.do(sp.first(const.RESEARCH_ZERGLINGMETABOLICBOOST))

                if not err:
                    self._recent_build_orders_200_second[build_target] = 1

        elif build_target == const.CENTRIFICALHOOKS:
            bn = self.bot.units(const.BANELINGNEST).ready
            if self.can_afford(build_target) and bn.exists:
                err = await self.bot.do(bn.first(const.RESEARCH_CENTRIFUGALHOOKS))

                if not err:
                    self._recent_build_orders_200_second[build_target] = 1


    async def run(self):
        return await self.create_build_target()


class UnitManager(object):
    """
    Class for handling unit orders beyond training/construction. Involves:

    * Worker harvester management
    * Force management
        * Attacking enemy with a force
        * Defending against enemy with a force
    * Queen injection
    * Scouting
    * Overlord management
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

            await self.bot.do(worker.gather(mineral, queue=True))

    async def manage_minerals(self):
        await self.manage_mineral_saturation()

        # Move idle workers to mining
        for worker in self.bot.workers.idle:
            townhall = self.bot.townhalls.closest_to(worker.position)
            mineral = self.bot.state.mineral_field.closest_to(townhall)

            await self.bot.do(worker.gather(mineral))

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

                await self.bot.do(worker.gather(mineral, queue=True))

        # Move workers from minerals to unsaturated extractors
        if unsaturated_extractors:
            extractor = unsaturated_extractors.first

            mineral_workers = self.bot.workers.filter(
                lambda worker: worker.is_carrying_minerals)

            if mineral_workers.exists:
                worker = mineral_workers.closest_to(extractor)

                await self.bot.do(worker.gather(extractor, queue=True))


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
                        await self.bot.do(queen(const.EFFECT_INJECTLARVA, townhall))

    async def manage_scouts(self):
        pass

    async def manage_attacking(self):
        army = self.bot.units().filter(
            lambda unit: unit.type_id in const2.ZERG_ARMY_UNITS)

        # Value of the army
        army_value = sum([const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army])

        if army_value > 100:
            target = self.bot.known_enemy_structures.random_or(
                self.bot.enemy_start_locations[0]).position
            for unit in army:
                await self.bot.do(unit.attack(target))

    async def manage_forces(self):
        await self.manage_attacking()

    async def run(self):
        await self.manage_resources()
        await self.manage_queens()
        await self.manage_scouts()
        await self.manage_forces()


class LambdaBot(sc2.BotAI):
    def __init__(self):
        self.build_manager = BuildManager(self)
        self.build_manager.load_build_order(BUILD)

        self.unit_manager = UnitManager(self)

    async def on_step(self, iteration):
        hatchery = self.units(const.HATCHERY).ready.first
        larvae = self.units(const.LARVA)

        target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position

        await self.build_manager.run()
        await self.unit_manager.run()

        async def unused():
            if iteration == 0:
                await self.chat_send("(glhf)")


            if not self.units(const.HATCHERY).ready.exists:
                for unit in self.workers | self.units(const.ZERGLING) | self.units(const.QUEEN):
                    self.do(unit.attack(self.enemy_start_locations[0]))
                return

            if len(self.units(ZERGLING)) > 20:
                for zl in self.units(ZERGLING).idle:
                    await self.do(zl.attack(target))

            for queen in self.units(QUEEN).idle:
                abilities = await self.get_available_abilities(queen)
                if const.AbilityId.EFFECT_INJECTLARVA in abilities:
                    await self.do(queen(EFFECT_INJECTLARVA, hatchery))

            if self.vespene >= 100:
                sp = self.units(SPAWNINGPOOL).ready
                if sp.exists and self.minerals >= 100 and not self.mboost_started:
                    await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))
                    self.mboost_started = True

                if not self.moved_workers_from_gas:
                    self.moved_workers_from_gas = True
                    for drone in self.workers:
                        m = self.state.mineral_field.closer_than(10, drone.position)
                        await self.do(drone.gather(m.random, queue=True))

            if self.supply_left < 2:
                if self.can_afford(OVERLORD) and larvae.exists:
                    await self.do(larvae.train(OVERLORD))

            if self.units(SPAWNINGPOOL).ready.exists:
                if larvae.exists and self.can_afford(ZERGLING):
                    await self.do(larvae.random.train(ZERGLING))

            if self.units(EXTRACTOR).ready.exists and not self.moved_workers_to_gas:
                self.moved_workers_to_gas = True
                extractor = self.units(EXTRACTOR).first
                for drone in self.workers.random_group_of(3):
                    await self.do(drone.gather(extractor))

            if self.minerals > 500:
                    self.spawning_pool_started = True
                    await self.build(HATCHERY, near=hatchery)

            if self.drone_counter < 3:
                if self.can_afford(DRONE):
                    self.drone_counter += 1
                    await self.do(larvae.random.train(DRONE))

            if not self.extractor_started:
                if self.can_afford(EXTRACTOR):
                    drone = self.workers.random
                    target = self.state.vespene_geyser.closest_to(drone.position)
                    err = await self.do(drone.build(EXTRACTOR, target))
                    if not err:
                        self.extractor_started = True

            elif not self.spawning_pool_started:
                if self.can_afford(SPAWNINGPOOL):
                    for d in range(4, 15):
                        pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                        if await self.can_place(SPAWNINGPOOL, pos):
                            drone = self.workers.closest_to(pos)
                            err = await self.do(drone.build(SPAWNINGPOOL, pos))
                            if not err:
                                self.spawning_pool_started = True
                                break

            elif not self.queeen_started and self.units(SPAWNINGPOOL).ready.exists:
                if self.can_afford(QUEEN):
                    r = await self.do(hatchery.train(QUEEN))
                    if not r:
                        self.queeen_started = True