import copy
import math
from typing import Iterable, List, Tuple

import lib.sc2 as sc2
from lib.sc2.position import Point2
from lib.sc2.unit import Unit
import lib.sc2.constants as const

import lambdanaut.const2 as const2
from lambdanaut.const2 import Messages
from lambdanaut.expiringlist import ExpiringList
from lambdanaut.managers import Manager
from lambdanaut.pathfinding import Pathfinder
import lambdanaut.utils as utils


class MicroManager(Manager):
    """
    Manager for microing army units
    """

    name = 'Micro Manager'

    def __init__(self, bot):
        super(MicroManager, self).__init__(bot)

        self.healing_roaches_tags = set()
        self.healing_infestors_tags = set()

        # We only want to send a single bile at each force field.
        # Tag the biled ones.
        self.biled_forcefields = set()

        # Subscribe to messages
        self.subscribe(Messages.UNROOT_ALL_SPINECRAWLERS)
        self.subscribe(Messages.STRUCTURE_COMPLETE)

        # Track the last fungal growth used
        # Because the sc2 protocol doesn't let us see buffs on enemies, we only allow
        # one fungal per 2 game seconds.
        self._fungals_used = ExpiringList()

    async def micro_back_melee(self, unit) -> bool:
        """
        Micros back damaged melee units
        Returns a boolean indicating whether they were micro'd back

        CURRENTLY NOT IN USE BECAUSE IT DOESN'T SEEM TO PROVIDE ANY BENEFITS
        WOULD THEORETICALLY BE USED BY WORKERS AND ZERGLINGS
        """
        if unit.health_percentage < 0.25:
            if self.bot.known_enemy_units:
                nearest_enemy = self.bot.known_enemy_units.closest_to(unit)
                if nearest_enemy.distance_to(unit) < 12 and self.bot.is_melee(nearest_enemy):
                    away_from_enemy = unit.position.towards(nearest_enemy, -1)
                    self.bot.actions.append(unit.move(away_from_enemy))
                    return True
        return False

    async def manage_workers(self):
        pass

    async def manage_zerglings(self):
        zerglings = self.bot.units(const.ZERGLING)

        attack_priority_types = const2.WORKERS

        # Micro zerglings
        for zergling in zerglings:

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
                                distance_to_enemy < 5.5 and \
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

        attack_priorities = const2.WORKERS | {
            const.MARINE, const.ZERGLING, const.ZEALOT, const.SUPPLYDEPOT}

        # Splash action to perform on enemies
        def splash_action(baneling, enemy):
            if baneling.distance_to(enemy) < 2:
                self.bot.actions.append(baneling.attack(enemy))
            else:
                self.bot.actions.append(baneling.move(enemy.position))

        # Micro banelings towards priority targets, calling `splash_action` on them.
        self.bot.splash_on_enemies(
            units=banelings,
            action=splash_action,
            search_range=10,
            priorities=attack_priorities,)

        # Unburrow banelings if enemy nearby
        for baneling in burrowed_banelings:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(2, baneling)
            if len(nearby_enemy_units) > 4:
                # Unburrow baneling
                self.bot.actions.append(baneling(const.BURROWUP_BANELING))

    async def manage_roaches(self):
        roaches = self.bot.units(const.ROACH)

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
                    nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, roach).not_structure
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
            const.SCV, const.OVERLORD, const.MEDIVAC, const.SIEGETANKSIEGED, const.BANSHEE,
            const.PHOTONCANNON, const.SPINECRAWLER, const.PYLON, const.SUPPLYDEPOT,
            const.FACTORYTECHLAB, const.STARPORTTECHLAB,
        }
        bile_priorities_neutral = {
            const.UnitTypeId.FORCEFIELD,
        }

        for ravager in ravagers:
            nearby_enemy_units = self.bot.enemy_cache.values()
            nearby_enemy_units = [u.snapshot for u in nearby_enemy_units if u.distance_to(ravager) < 14 + u.radius]
            if nearby_enemy_units:
                # Perform bile attacks
                # Bile range is 9
                nearby_enemy_priorities = [u for u in nearby_enemy_units if u.type_id in bile_priorities]
                nearby_enemy_priorities += self.bot.state.units(bile_priorities_neutral)

                # Prefer targeting our bile_priorities
                nearby_enemy_priorities = nearby_enemy_priorities \
                    if nearby_enemy_priorities else nearby_enemy_units

                abilities = await self.bot.get_available_abilities(ravager)
                for enemy_unit in sorted(nearby_enemy_priorities,
                                         key=lambda unit: ravager.distance_to(unit)):

                    can_cast = await self.bot.can_cast(ravager, const.AbilityId.EFFECT_CORROSIVEBILE,
                                                       enemy_unit.position,
                                                       cached_abilities_of_unit=abilities,
                                                       only_check_energy_and_cooldown=True)
                    if can_cast:
                        if enemy_unit.is_structure:
                            # Bile at the edge of structure's radius so we don't have to get close
                            target = enemy_unit.position.towards(ravager.position, enemy_unit.radius)
                        else:
                            # Bile slightly behind the enemy unit so they are forced forwards
                            target = enemy_unit.position.towards(ravager.position, -enemy_unit.radius * 0.8)

                        our_closest_unit_to_enemy = self.bot.units.closest_to(target)
                        if our_closest_unit_to_enemy.distance_to(enemy_unit.position) > 3:

                            # Only bile a forcefield at most once
                            if enemy_unit.type_id == const.UnitTypeId.FORCEFIELD:
                                if enemy_unit.tag in self.biled_forcefields:
                                    continue
                                self.biled_forcefields.add(enemy_unit.tag)

                            self.bot.actions.append(ravager(const.EFFECT_CORROSIVEBILE, target))
                            break
                else:
                    # If we're not using bile, then micro ravagers
                    enemies_to_avoid = {const.PHOTONCANNON, const.BUNKER, const.SPINECRAWLER}
                    nearby_enemy_units = [u for u in nearby_enemy_units
                                          if u.can_attack_ground or u.type_id in enemies_to_avoid]
                    if nearby_enemy_units:
                        closest_enemy = ravager.position.closest(nearby_enemy_units)
                        nearby_friendly_units = self.bot.units.closer_than(15, ravager)

                        if closest_enemy.type_id in enemies_to_avoid and len(nearby_friendly_units) < 12:
                            # Keep out of range of dangerous enemy structures if our ravager army is small
                            # Disregard unpowered photon cannons
                            if closest_enemy.type_id is not const.PHOTONCANNON \
                                    or (closest_enemy.type_id is const.PHOTONCANNON and closest_enemy.is_powered):

                                if closest_enemy.type_id is const.BUNKER:
                                    # Assume the maximum bunker range of 7 (Marauder +1)
                                    enemy_range = 7
                                else:
                                    enemy_range = closest_enemy.ground_range

                                distance_to_enemy = ravager.distance_to(closest_enemy)
                                ravager_in_range = distance_to_enemy < enemy_range + 3.5

                                if ravager_in_range:
                                    away_from_enemy = ravager.position.towards(closest_enemy, -2)
                                    self.bot.actions.append(ravager.move(away_from_enemy))
                                    self.bot.actions.append(ravager.hold_position(queue=True))

                        elif ravager.weapon_cooldown \
                                and closest_enemy.distance_to(ravager) <= ravager.ground_range:

                            # Move a bit further if the enemy is a unit rather than a structure
                            distance_to_move = 1 if closest_enemy.is_structure else 2

                            away_from_enemy = ravager.position.towards(closest_enemy, -distance_to_move)

                            pathable = not self.bot.game_info.pathing_grid.is_set(away_from_enemy.rounded)
                            if pathable:
                                self.bot.actions.append(ravager.move(away_from_enemy))
                                self.bot.actions.append(ravager.attack(closest_enemy.position, queue=True))

    async def manage_infestors(self):
        infestors = self.bot.units(const.INFESTOR)
        burrowed_infestors = self.bot.units(const.UnitTypeId.INFESTORBURROWED)

        if infestors or burrowed_infestors:

            fungal_priorities = const2.WORKERS | {
                const.ZERGLING, const.BANELING, const.HYDRALISK, const.ROACH, const.MUTALISK, const.CORRUPTOR,
                const.BROODLORD,
                const.MARINE, const.MARAUDER, const.REAPER, const.GHOST, const.VIKING, const.BANSHEE, const.MEDIVAC,
                const.HELLION, const.HELLIONTANK,
                const.ZEALOT, const.STALKER, const.ADEPT, const.DARKTEMPLAR, const.VOIDRAY, const.TEMPEST,
                const.SENTRY, const.HIGHTEMPLAR, const.PHOENIX,}

            infested_terran_priorities = const2.TOWNHALLS | {
                const.SIEGETANKSIEGED, const.CARRIER, const.PHOENIX, const.BROODLORD, const.ULTRALISK,
                const.PHOTONCANNON, const.SPINECRAWLER, const.BUNKER
            }

            def splash_action(infestor, enemy):
                """Splash action to perform on enemies during fungal growths"""
                if infestor.distance_to(enemy) >= 12:
                    towards_enemy = infestor.position.towards(enemy, 1)
                    self.bot.actions.append(infestor.move(towards_enemy))
                else:
                    self.bot.actions.append(infestor(
                        const.AbilityId.FUNGALGROWTH_FUNGALGROWTH, enemy.position))

                    # Record the fungal we used so we don't fungal again for 1 seconds
                    self._fungals_used.add(True, self.bot.state.game_loop, expiry=1)

            # Splash condition that must be passed on the enemy unit to fungal him
            # We don't want to re-fungal already fungalled units
            def splash_condition(enemy) -> bool:
                """ TODO: This is broken. you can't see enemy buffs. Hope this is changed in the protocol."""
                return not enemy.has_buff(const.BuffId.FUNGALGROWTH)

            if not self._fungals_used.contains(True, self.bot.state.game_loop):
                # Perform fungal growths on clumps of enemies
                fungal_infestors = infestors.filter(lambda i: i.energy >= 75)
                self.bot.splash_on_enemies(
                    units=fungal_infestors,
                    action=splash_action,
                    search_range=14,
                    condition=splash_condition,
                    min_enemies=5,
                    priorities=fungal_priorities,)

            for infestor in infestors | burrowed_infestors:
                if const.BURROW in self.bot.state.upgrades \
                        and not infestor.is_burrowed \
                        and infestor.health_percentage < 0.40:
                    # Burrow damaged infestors

                    # Move away from the direction we're facing
                    target = utils.towards_direction(infestor.position, infestor.facing, -20)

                    # Tag infestor as a healing infestor
                    self.healing_infestors_tags.add(infestor.tag)

                    self.bot.actions.append(infestor(const.AbilityId.BURROWDOWN_INFESTOR))
                    self.bot.actions.append(infestor.move(target, queue=True))
                else:
                    cluster = infestor.position.closest(self.bot.army_clusters)
                    if cluster:
                        nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, infestor)

                        if nearby_enemy_units:
                            nearby_enemy_priorities = nearby_enemy_units.of_type(infested_terran_priorities)
                            if infestor.energy >= 25 and nearby_enemy_priorities:
                                # Throw infested terran eggs at infested terran priorities
                                nearby_enemy_priority = nearby_enemy_priorities.closest_to(infestor)
                                self.bot.actions.append(infestor(
                                    const.AbilityId.INFESTEDTERRANS_INFESTEDTERRANS,
                                    nearby_enemy_priority.position))
                            elif nearby_enemy_units.closer_than(7, infestor):
                                # Move infestors away from nearby enemies
                                closest_enemy = nearby_enemy_units.closest_to(infestor.position)
                                target = cluster.position.towards(closest_enemy, -3)

                                self.bot.actions.append(infestor.move(target))

        # Unburrow healed infestors
        to_remove_from_healing = set()
        for infestor_tag in self.healing_infestors_tags:
            infestor = self.bot.units.find_by_tag(infestor_tag)
            if infestor:
                if infestor.health_percentage > 0.96:
                    nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, infestor).not_structure
                    if not nearby_enemy_units or len(nearby_enemy_units) < 2:
                        # Untag infestor as a healing infestor
                        to_remove_from_healing.add(infestor_tag)

                        # Unburrow infestor
                        self.bot.actions.append(infestor(const.AbilityId.BURROWUP_INFESTOR))
            else:
                to_remove_from_healing.add(infestor_tag)

    async def manage_mutalisks(self):
        """
        Mutalisk pathfinding

        * If
          * Priority within 40 of Mutalisk
          * AND priority is further than Mutalisk attack range
          * AND No nearby ranged air units can hit us
        * Generate pixelmap of air-ranged enemy units
        * Get path to priority around air-ranged enemy units
        * Queue up path to priority and follow it
        *
        """
        mutalisks = self.bot.units(const.MUTALISK)

        if mutalisks:
            attack_priorities = const2.WORKERS | {
                const.SIEGETANK, const.SIEGETANKSIEGED, const.MEDIVAC,
                const.IMMORTAL,
                const.BROODLORD,
            }

            # Make a copy of a blank pixel map to draw on
            pixel_map = copy.deepcopy(self.bot.blank_pixel_map)

            # Get enemy units that can attack air
            enemy_units = [u.snapshot for u in self.bot.enemy_cache.values() if u.can_attack_air]

            # Filter enemy_priorities for ones far enough from enemy air attackers
            # Subtract two from air range to conservatively account for mutalisk's range (3)
            enemy_priorities = [u.snapshot for u in self.bot.enemy_cache.values()
                                if u.type_id in attack_priorities
                                and all(u.distance_to(enemy) > enemy.air_range
                                        for enemy in enemy_units)]

            if enemy_priorities:

                # Flood fill the pixel map with enemy unit ranges
                utils.draw_unit_ranges(enemy_units)

                # Get mutalisks that are in range of enemy units.
                mutalisks_in_range_of_enemy = [mu for mu in mutalisks
                                               if any(u.target_in_range(mu) for u in enemy_units)]

                for mutalisk in mutalisks:
                    if not mutalisk.is_attacking and not mutalisk.is_moving \
                            or mutalisks_in_range_of_enemy:
                        nearest_priority = mutalisk.position.closest(enemy_priorities)

                        mutalisk_pos = mutalisk.position.rounded
                        priority_pos = nearest_priority.position.rounded

                        pathfinder = Pathfinder(pixel_map)

                        path = pathfinder.find_path(mutalisk_pos, priority_pos)

                        if not path:
                            continue

                        # Convert path to list and use only every 3rd step
                        path: List[Point2] = [p for p in path][::3]

                        # Issue move commands
                        for p in path[1:-1]:
                            self.bot.actions.append(mutalisk.move(p, queue=True))

                        self.bot.actions.append(mutalisk.attack(nearest_priority, queue=True))

    async def manage_corruptors(self):
        corruptors = self.bot.units(const.CORRUPTOR)
        if corruptors:
            army = self.bot.units(const2.ZERG_ARMY_UNITS)
            if army:
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

            if army:
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

        if spine_crawlers and townhalls:
            townhall = townhalls.furthest_to(self.bot.start_location)

            # Get nearby spinecrawlers that are at our elevation
            nearby_spine_crawlers = spine_crawlers.closer_than(22, townhall).filter(
                lambda sc: math.floor(sc.position3d.z) <= math.floor(townhall.position3d.z))

            # Get nearby ramp
            nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
            nearby_ramp: Point2 = townhall.position.towards(
                self.bot.enemy_start_location, 2).closest(nearby_ramps)

            try:
                ramp_height = self.bot.game_info.terrain_height[nearby_ramp]
            except:
                ramp_height = None

            try:
                ramp_creep = self.bot.state.creep.is_set(nearby_ramp)
            except:
                ramp_creep = False

            ramp_distance_to_sc = nearby_ramp.distance_to_closest(spine_crawlers)

            ramp_lower_than_townhall = ramp_height is not None \
                and math.floor(ramp_height) <= math.floor(townhall.position3d.z)

            ramp_close_to_townhall = nearby_ramp.distance_to(townhall) < 20

            # Unroot spine crawlers that are far away from the front expansions
            # Also unroot spine crawlers if a nearby ramp gets creep on it.
            if len(nearby_spine_crawlers) < len(spine_crawlers) \
                    or (ramp_close_to_townhall and ramp_lower_than_townhall and ramp_creep
                        and ramp_distance_to_sc > 2):

                far_rooted_spine_crawlers = (sc for sc in rooted_spine_crawlers.idle
                                             if sc not in nearby_spine_crawlers)
                for sc in far_rooted_spine_crawlers:
                    self.bot.actions.append(sc(
                        const.AbilityId.SPINECRAWLERUPROOT_SPINECRAWLERUPROOT))

            # Root unrooted spine crawlers near the front expansions
            idle_uprooted_spine_crawlers = uprooted_spine_crawlers.idle
            if idle_uprooted_spine_crawlers:
                # We do this one by one rather than in a for-loop so that they don't
                # try to root at the same place as each other
                sc = idle_uprooted_spine_crawlers.first
                if ramp_close_to_townhall \
                        and ramp_lower_than_townhall:
                    target = nearby_ramp
                else:
                    near_townhall = townhall.position.towards_with_random_angle(
                        self.bot.enemy_start_location, 10)
                    target = near_townhall

                position = await self.bot.find_placement(
                    const.SPINECRAWLER, target, max_distance=25)

                self.bot.actions.append(
                    sc(const.AbilityId.SPINECRAWLERROOT_SPINECRAWLERROOT, position))

    async def manage_structures(self):
        structures = self.bot.units.structure

        # Cancel damaged not-ready structures
        for structure in structures.not_ready:
            if structure.health_percentage < 0.08 or \
                    (structure.build_progress > 0.98 and structure.health_percentage < 0.35):
                self.bot.actions.append(structure(const.CANCEL))

    async def manage_eggs(self):
        # egg_types = {const.BROODLORDCOCOON, const.RAVAGERCOCOON, const.BANELINGCOCOON,
        #              const.LURKERMPEGG, const.UnitTypeId.EGG}
        egg_types = {const.UnitTypeId.EGG}
        eggs = self.bot.units(egg_types)

        # Cancel damaged not-ready structures
        for egg in eggs:
            if egg.health_percentage < 0.1 and 0.03 < egg.build_progress < 0.95:
                self.bot.actions.append(egg(const.CANCEL))

    def avoid_effects(self):
        """
        Avoid incoming enemy effects (Biles, Psi storms, Lurkers, etc)

        This value should be set in the cached unit
        """

        units = self.bot.unit_cache.values()

        for unit in units:
            if unit.avoiding_effect is not None:
                target = unit.avoiding_effect.towards(unit.position, 4)
                self.bot.actions.append(unit.move(target))

    async def manage_priority_targeting(self, unit: Unit, attack_priorities=None) -> bool:
        """Handles combat priority targeting for the given unit"""

        if unit.is_collecting:
            # Don't priority target if it's a mining worker
            return False

        enemy_units = self.bot.known_enemy_units
        if enemy_units:
            if self.bot.is_melee(unit):
                # Search for further priorities if unit is melee
                enemy_units = enemy_units.closer_than(2, unit)
            else:
                enemy_units = enemy_units.closer_than(unit.ground_range * 1.8, unit)

            if enemy_units:
                target = self.bot.closest_and_most_damaged(
                    enemy_units, unit, priorities=attack_priorities)
                if target:
                    self.bot.actions.append(unit.attack(target))
                    return True
        return False

    async def manage_combat_micro(self):
        """Does default combat micro for units"""

        types_not_to_micro = {const.LURKERMP, const.MUTALISK, const.INFESTEDTERRAN, const.ROACHBURROWED,
                              const.INFESTORBURROWED, const.BROODLORD}

        # Micro closer to nearest enemy army cluster if our dps is higher
        # Micro further from nearest enemy army cluster if our dps is lower
        for army_cluster in self.bot.army_clusters:
            army_center = army_cluster.position

            nearest_enemy_cluster = army_center.closest(self.bot.enemy_clusters)
            enemy_army_center = nearest_enemy_cluster.position

            nearby_army = [u for u in army_cluster if u.type_id not in types_not_to_micro]
            if army_center.distance_to(enemy_army_center) < 17:
                # Micro against enemy clusters
                if nearby_army and nearest_enemy_cluster:
                    army_strength = self.bot.relative_army_strength(army_cluster, nearest_enemy_cluster)

                    ranged_units_in_attack_range_count = self.bot.count_units_in_attack_range(
                        nearby_army, nearest_enemy_cluster, ranged_only=True)
                    ranged_units_in_attack_range_ratio = ranged_units_in_attack_range_count / len(nearby_army)

                    nearby_workers = [u.snapshot for u in self.bot.enemy_cache.values()
                                      if u.type_id in const2.WORKERS and u.distance_to(army_center) < 35]

                    for unit in nearby_army:
                        if unit.movement_speed > 0 and not unit.is_collecting:

                            # If there are no enemies that we want to attack nearby, but there are workers,
                            # then attack the workers
                            attackable_non_workers = \
                                [u for u in self.bot.known_enemy_units.ready
                                 if self.bot.can_attack(unit, u)
                                 and u.type_id not in const2.WORKERS
                                 and (not u.is_structure or u.type_id in const2.DEFENSIVE_STRUCTURES)]

                            nearest_enemy_unit = unit.position.closest(nearest_enemy_cluster)
                            unit_is_combatant = unit.type_id not in const2.NON_COMBATANTS

                            # Don't micro a unit if he's avoiding an effect
                            if unit.avoiding_effect is not None:
                                pass

                            # Attack the closest worker if there are no attackable nearby units
                            elif not attackable_non_workers and nearby_workers and not unit.is_moving:
                                closest_worker = unit.position.closest(nearby_workers)
                                self.bot.actions.append(unit.snapshot.attack(closest_worker))

                            # Back off from enemy if our cluster is much weaker
                            elif army_strength < -5 and unit_is_combatant:
                                if self.bot.is_melee(unit):
                                    away_from_enemy = unit.position.towards(
                                        nearest_enemy_unit, -2)
                                    self.bot.actions.append(unit.snapshot.move(away_from_enemy))
                                    # away_from_enemy = army_center.towards(
                                    #     nearest_enemy_unit, -7)
                                    # self.bot.actions.append(unit.move(away_from_enemy))
                                elif unit.weapon_cooldown:
                                    # Ranged units only move back while we're on cooldown
                                    away_from_enemy = unit.position.towards(
                                        nearest_enemy_unit, -2)
                                    self.bot.actions.append(unit.snapshot.move(away_from_enemy))
                            # Close the distance if our cluster isn't in range
                            elif unit_is_combatant and ranged_units_in_attack_range_ratio < 0.8 \
                                    and len(army_cluster) > 6 \
                                    and unit.weapon_cooldown \
                                    and unit.distance_to(nearest_enemy_unit) - nearest_enemy_unit.radius > unit.ground_range * 0.35 \
                                    and not self.bot.is_melee(unit) \
                                    and not unit.is_moving:
                                how_far_to_move = 1
                                towards_enemy = unit.position.towards(
                                    nearest_enemy_unit, how_far_to_move)
                                self.bot.actions.append(unit.snapshot.move(towards_enemy))

                            # Handle combat priority targeting
                            else:
                                priorities = const2.WORKERS | {
                                    const.STARPORTTECHLAB, const.FACTORYTECHLAB,
                                    const.SIEGETANK, const.SIEGETANKSIEGED, const.MEDIVAC, const.CYCLONE,
                                    const.COLOSSUS, const.WARPPRISM, const.ARCHON, const.HIGHTEMPLAR,
                                    const.DARKTEMPLAR, const.DISRUPTOR,
                                    const.INFESTOR, const.QUEEN, const.LURKERMP, const.LURKERMPBURROWED,
                                    const.ULTRALISK, const.BROODLORD,
                                }
                                await self.manage_priority_targeting(unit.snapshot, attack_priorities=priorities)

    async def read_messages(self):
        """
        Reads incoming subscribed messages and performs micro adjustments and actions"""

        for message, val in self.messages.items():

            # Messages indicating that we should unroot and reposition spine crawlers
            if message is Messages.UNROOT_ALL_SPINECRAWLERS:
                self.ack(message)

                rooted_spine_crawlers = self.bot.units(const.SPINECRAWLER).ready
                for sc in rooted_spine_crawlers.idle:
                    self.bot.actions.append(sc(
                        const.AbilityId.SPINECRAWLERUPROOT_SPINECRAWLERUPROOT))

    async def run(self):
        await super(MicroManager, self).run()

        # Read and respond to messages
        await self.read_messages()

        # Do combat micro (moving closer/further away from enemy units)
        await self.manage_combat_micro()

        self.avoid_effects()

        await self.manage_workers()
        await self.manage_zerglings()
        await self.manage_banelings()
        await self.manage_roaches()
        await self.manage_ravagers()
        await self.manage_infestors()
        await self.manage_mutalisks()
        await self.manage_corruptors()
        await self.manage_overseers()
        await self.manage_changelings()
        await self.manage_spine_crawlers()
        await self.manage_structures()
        await self.manage_eggs()
