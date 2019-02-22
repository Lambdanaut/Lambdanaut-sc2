import math
from typing import Dict

import lib.sc2 as sc2
from lib.sc2.position import Point2
import lib.sc2.constants as const

import lambdanaut.const2 as const2
from lambdanaut.const2 import Messages
from lambdanaut.managers import Manager
import lambdanaut.utils as utils


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

        # Subscribe to messages
        self.subscribe(Messages.UNROOT_ALL_SPINECRAWLERS)
        self.subscribe(Messages.STRUCTURE_COMPLETE)

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

        # for baneling in banelings:
        #     nearby_enemy_units = self.bot.known_enemy_units.closer_than(10, baneling)
        #     nearby_enemy_priorities = nearby_enemy_units.of_type(attack_priorities)
        #
        #     if nearby_enemy_priorities:
        #         # Get the nearby priority target with the most nearby priority targets around it
        #
        #         greatest_count = 0
        #         greatest_i = 0
        #         for u_i in range(len(nearby_enemy_priorities)):
        #             u = nearby_enemy_priorities[u_i]
        #
        #             u_nearby_enemy_count = nearby_enemy_priority_counts.get(u.tag)
        #
        #             if u_nearby_enemy_count is None:
        #                 u_nearby_enemy_count = len(nearby_enemy_units.closer_than(3, u))
        #                 nearby_enemy_priority_counts[u.tag] = u_nearby_enemy_count
        #
        #             if u_nearby_enemy_count > greatest_count:
        #                 greatest_count = u_nearby_enemy_count
        #                 greatest_i = u_i
        #
        #         greatest_priority = nearby_enemy_priorities[greatest_i]


        # Unburrow banelings if enemy nearby
        for baneling in burrowed_banelings:
            nearby_enemy_units = self.bot.known_enemy_units.closer_than(2, baneling)
            if len(nearby_enemy_units) > 4:
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

    async def manage_infestors(self):
        infestors = self.bot.units(const.INFESTOR)

        if infestors:

            fungal_priorities = const2.WORKERS | {
                const.ZERGLING, const.BANELING, const.HYDRALISK, const.ROACH, const.MUTALISK, const.CORRUPTOR,
                const.BROODLORD,
                const.MARINE, const.MARAUDER, const.REAPER, const.GHOST, const.VIKING, const.BANSHEE, const.MEDIVAC,
                const.ZEALOT, const.DARKTEMPLAR, const.STALKER, const.ADEPT, const.VOIDRAY, const.TEMPEST,
                const.SENTRY, const.HIGHTEMPLAR, }

            # Splash action to perform on enemies during fungal growths
            def splash_action(infestor, enemy):
                if infestor.distance_to(enemy) > 11:
                    towards_enemy = infestor.position.towards(enemy, 1)
                    self.bot.actions.append(infestor.move(towards_enemy))
                else:
                    self.bot.actions.append(infestor(
                        const.AbilityId.FUNGALGROWTH_FUNGALGROWTH, enemy.position))

            # Splash condition that must be passed on the enemy unit to fungal him
            # We don't want to re-fungal already fungalled units
            def splash_condition(enemy) -> bool:
                """ TODO: This is broken. you can't see enemy buffs. Hope this is changed in the protocol."""
                return not enemy.has_buff(const.BuffId.FUNGALGROWTH)

            # Perform fungal growths on clumps of enemies
            fungal_infestors = infestors.filter(lambda i: i.energy >= 75)
            self.bot.splash_on_enemies(
                units=fungal_infestors,
                action=splash_action,
                search_range=14,
                condition=splash_condition,
                min_enemies=5,
                priorities=fungal_priorities,)

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
        egg_types = {const.BROODLORDCOCOON, const.RAVAGERCOCOON, const.BANELINGCOCOON,
                     const.LURKERMPEGG, const.UnitTypeId.EGG}
        eggs = self.bot.units(egg_types)

        # Cancel damaged not-ready structures
        for egg in eggs:
            if egg.health_percentage < 0.1 and 0.03 < egg.build_progress < 0.95:
                self.bot.actions.append(egg(const.CANCEL))

    async def avoid_biles(self):
        """Avoid incoming bile attacks"""
        for bile in filter(lambda e: e.id == const.EffectId.RAVAGERCORROSIVEBILECP,
                           self.bot.state.effects):

            for position in bile.positions:
                units = self.bot.units.closer_than(1.5, position)

                if units.exists:
                    for unit in units:
                        target = position.towards(unit.position, 2)
                        self.bot.actions.append(unit.move(target))

    async def manage_priority_targeting(self, unit, attack_priorities=None):
        """Handles combat priority targeting for the given unit"""

        if unit.is_collecting:
            # Don't priority target if it's a mining worker
            return

        if attack_priorities is None:
            attack_priorities = set()

        enemy_units = self.bot.known_enemy_units
        if enemy_units:
            if self.bot.is_melee(unit):
                # Search for further priorities if unit is melee
                enemy_units = enemy_units.closer_than(3, unit)
            else:
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

            types_not_to_move = {const.LURKERMP}
            nearby_army = [u.snapshot for u in army_cluster if u.type_id not in types_not_to_move]
            if army_center.distance_to(enemy_army_center) < 17:
                # Micro against enemy clusters
                if nearby_army and nearest_enemy_cluster:
                    army_strength = self.bot.relative_army_strength(army_cluster, nearest_enemy_cluster)

                    for unit in nearby_army:
                        if unit.movement_speed > 0 and \
                                not unit.is_moving:
                            nearest_enemy_unit = unit.position.closest(nearest_enemy_cluster)
                            unit_is_combatant = unit.type_id not in const2.NON_COMBATANTS

                            # Back off from enemy if our cluster is much weaker
                            if army_strength < -5 and unit_is_combatant:
                                if self.bot.is_melee(unit):
                                    away_from_enemy = unit.position.towards(
                                        nearest_enemy_unit, -2)
                                    self.bot.actions.append(unit.move(away_from_enemy))
                                    # away_from_enemy = army_center.towards(
                                    #     nearest_enemy_unit, -7)
                                    # self.bot.actions.append(unit.move(away_from_enemy))
                                elif unit.weapon_cooldown:
                                    # Ranged units only move back while we're on cooldown
                                    away_from_enemy = unit.position.towards(
                                        nearest_enemy_unit, -2)
                                    self.bot.actions.append(unit.move(away_from_enemy))

                            # If nearest enemy unit is melee and our cluster is small, back off
                            elif 0 < nearest_enemy_unit.ground_range < 1.5 and len(army_cluster) < 8 \
                                    and unit.ground_range > 1 and nearest_enemy_unit.distance_to(unit) > 0.5 \
                                    and unit_is_combatant:
                                how_far_to_move = -1
                                away_from_enemy = unit.position.towards(
                                    nearest_enemy_unit, how_far_to_move)
                                self.bot.actions.append(unit.move(away_from_enemy))
                                self.bot.actions.append(unit.attack(unit.position, queue=True))

                            # If nearest enemy unit is ranged close the distance if our cluster is stronger
                            elif army_strength > 2 and \
                                    unit_is_combatant:
                                distance_to_enemy_unit = unit.distance_to(nearest_enemy_unit)
                                if unit.ground_range > 1 and \
                                        distance_to_enemy_unit > unit.ground_range * 0.5 and \
                                        not unit.is_moving and unit.weapon_cooldown <= 0:
                                    how_far_to_move = distance_to_enemy_unit * 0.6
                                    towards_enemy = unit.position.towards(
                                        nearest_enemy_unit, how_far_to_move)
                                    self.bot.actions.append(unit.move(towards_enemy))

                            # Handle combat priority targeting
                            elif not unit.weapon_cooldown or unit.is_attacking:
                                priorities = const2.WORKERS | {const.SIEGETANK, const.SIEGETANKSIEGED, const.QUEEN,
                                                               const.COLOSSUS, const.MEDIVAC, const.WARPPRISM}
                                await self.manage_priority_targeting(unit, attack_priorities=priorities)

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

        await self.avoid_biles()
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
