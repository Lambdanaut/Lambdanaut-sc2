from collections import Counter

import lib.sc2 as sc2
import lib.sc2.constants as const

from lambdanaut.builds import BuildStages
from lambdanaut.expiringlist import ExpiringList
import lambdanaut.const2 as const2
from lambdanaut.const2 import ForcesStates, Messages
from lambdanaut.managers import Manager


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
        self.has_scouted_enemy_rush = False
        self.has_scouted_enemy_worker_rush = False
        self.has_published_need_more_enemy_tech_intel = False
        self.has_published_scouted_enemy_tech_intel = False
        self.has_published_scouted_enemy_proxy_hatchery = False
        self.has_published_scouted_greedy_early_opponent = False
        self.has_published_research_neural_parasite = False
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
                self.bot.update_shortest_path_to_enemy_start_location()

    def enemy_counter_with_midgame_broodlord_rush(self) -> bool:
        """Checks the map to see if there are any visible units we should counter with a broodlord rush"""
        if not self.has_scouted_enemy_counter_midgame_broodlord_rush:

            factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            tank_count = len(self.bot.known_enemy_units.of_type(
                {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if factory_count > 2 or tank_count > 3:
                self.has_scouted_enemy_counter_midgame_broodlord_rush = True
                return True

        return False

    def enemy_counter_with_midgame_roach_spotted(self) -> bool:
        """Checks the map to see if there are any visible units we should counter with roach/hydra"""
        if not self.has_scouted_enemy_counter_with_roaches:
            enemy_counter_with_roach_types = {
                const.ROACH, const.ROACHWARREN,
            }

            enemy_counter_with_roach_units = self.bot.known_enemy_units.of_type(enemy_counter_with_roach_types)

            # Removed countering with roaches vs Terran

            # factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            # reaper_count = len(self.bot.known_enemy_units.of_type(const.REAPER))
            # tank_count = len(self.bot.known_enemy_units.of_type(
            #     {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if enemy_counter_with_roach_units.exists:
                    # or factory_count > 1 \
                    # or tank_count > 1:
                self.has_scouted_enemy_counter_with_roaches = True
                return True

        return False

    def enemy_air_tech_scouted(self) -> bool:
        """Checks the map to see if there are any visible enemy air tech"""
        if not self.has_scouted_enemy_air_tech:
            enemy_air_tech_types = {
                const.STARGATE, const.SPIRE, const.LIBERATOR, const.BATTLECRUISER, const.ORACLE,
                const.BANSHEE, const.SMBANSHEE, const.SMARMORYBANSHEE,
                const.BROODLORD, const.DARKSHRINE, const.GHOSTACADEMY,
                const.GHOST, const.MUTALISK, const.LURKERDENMP, const.LURKERMP, const.ROACHBURROWED,
                const.STARPORTTECHLAB, const.DARKTEMPLAR, const.LURKER, const.LURKERDEN}

            enemy_air_tech_units = self.bot.known_enemy_units.of_type(enemy_air_tech_types)

            phoenix_count = len(self.bot.known_enemy_units.of_type(const.PHOENIX))

            if enemy_air_tech_units or phoenix_count > 2:
                self.has_scouted_enemy_air_tech = True
                return True

        return False

    def greater_enemy_force_scouted(self) -> bool:
        if not self.has_scouted_enemy_greater_force.contains(
                True, self.bot.state.game_loop):

            relative_army_strength = self.bot.relative_army_strength(
                self.bot.unit_cache.values(), self.bot.enemy_cache.values(),
                ignore_workers=True)

            if relative_army_strength < -2:
                self.has_scouted_enemy_greater_force.add(
                    True, self.bot.state.game_loop, expiry=30)
                return True

            return False

    def enemy_moving_out_scouted(self) -> bool:
        """
        Checks to see if enemy units are moving out towards us
        """
        enemy_units = self.bot.known_enemy_units
        exclude_nonarmy_types = const2.WORKERS | {const.OVERLORD, const.OVERSEER}
        enemy_units = enemy_units.exclude_type(exclude_nonarmy_types).not_structure.\
            closer_than(80, self.bot.enemy_start_location)

        closer_enemy_counts = 0
        if len(enemy_units) > 2:
            for enemy_unit in enemy_units:
                if self.bot.moving_closer_to(
                        unit=enemy_unit,
                        cache=self.bot.enemy_cache,
                        point=self.bot.start_location):
                    closer_enemy_counts += 1

            # At least 4 enemy units were spotted moving closer to us for 10 iterations
            # Also the force manager is not currently attacking or moving to attack
            if self.bot.force_manager.state not in {ForcesStates.ATTACKING, ForcesStates.MOVING_TO_ATTACK} and \
                    closer_enemy_counts > 3:
                self.has_scouted_enemy_rush = True
                return True

        return False

    def enemy_rush_scouted(self) -> bool:
        """
        Checks to see if we're being rushed
        """

        if not self.has_scouted_enemy_rush and \
                self.bot.build_manager.build_stage in {BuildStages.OPENING, BuildStages.EARLY_GAME}:

            enemy = self.bot.enemy_cache.values()

            units_to_count = const2.WORKERS | {const.ZERGLING, const.RAVAGER,
                        const.MARINE, const.REAPER, const.MARAUDER,
                        const.ZEALOT, const.ADEPT, const.STALKER}

            enemy_counter = Counter()
            nearby_enemy_counter = Counter()

            for unit in enemy:
                if unit.type_id in units_to_count:
                    enemy_counter[unit.type_id] += 1

                    proximity = unit.position.distance_to(self.bot.start_location)
                    if proximity < self.bot.start_location_to_enemy_start_location_distance * 0.75:
                        nearby_enemy_counter[unit.type_id] += 1

            # Count any and all enemy units
            if (
                    enemy_counter[const.ZERGLING] >= 7
                    or enemy_counter[const.RAVAGER] >= 2
                    or enemy_counter[const.MARINE] >= 6
                    or enemy_counter[const.REAPER] >= 3
                    or enemy_counter[const.MARAUDER] >= 4
                    or enemy_counter[const.ZEALOT] >= 4
                    or enemy_counter[const.ADEPT] >= 4
                    or enemy_counter[const.STALKER] >= 4):
                self.has_scouted_enemy_rush = True
                return True

            # Count nearby enemy units
            elif (
                    nearby_enemy_counter[const.DRONE] >= 5
                    or nearby_enemy_counter[const.ZERGLING] >= 4
                    or enemy_counter[const.RAVAGER] >= 1
                    or nearby_enemy_counter[const.SCV] >= 5
                    or nearby_enemy_counter[const.MARINE] >= 2
                    or nearby_enemy_counter[const.REAPER] >= 2
                    or nearby_enemy_counter[const.MARAUDER] >= 1
                    or nearby_enemy_counter[const.PROBE] >= 5
                    or nearby_enemy_counter[const.ZEALOT] >= 1
                    or nearby_enemy_counter[const.ADEPT] >= 3
                    or nearby_enemy_counter[const.STALKER] >= 2):
                self.has_scouted_enemy_rush = True
                return True

            return False

    def enemy_worker_rush_scouted(self):
        if not self.has_scouted_enemy_worker_rush and \
                self.bot.build_manager.build_stage in {BuildStages.OPENING, BuildStages.EARLY_GAME}:

            enemy = self.bot.enemy_cache.values()

            nearby_worker_count = len([
                u for u in enemy if u.type_id in const2.WORKERS
                and u.distance_to(self.bot.start_location) <
                self.bot.start_location_to_enemy_start_location_distance * 0.75])

            if nearby_worker_count > 5:
                self.has_scouted_enemy_worker_rush = True
                return True

    def need_more_enemy_tech_intel(self):
        """
        If we're in mid to late game and we've seen few enemy structures,
        publish a message to search for further enemy tech structures.
        """
        if not self.has_published_need_more_enemy_tech_intel \
                and not self.has_published_scouted_enemy_tech_intel \
                and len(self.bot.townhalls.ready) > 2:

            non_tech_structures = {const.SUPPLYDEPOT, const.PYLON}
            enemy_tech_structures = self.bot.known_enemy_structures.exclude_type(non_tech_structures)

            if len(enemy_tech_structures) < 3:
                self.has_published_need_more_enemy_tech_intel = True
                return True

        return False

    def scouted_enemy_tech_intel(self):
        if not self.has_published_scouted_enemy_tech_intel \
                and self.bot.build_manager.build_stage in {BuildStages.MID_GAME, BuildStages.LATE_GAME} \
                and len(self.bot.known_enemy_structures) > 4:

            non_tech_structures = {const.SUPPLYDEPOT, const.PYLON}
            enemy_tech_structures = self.bot.known_enemy_structures.exclude_type(non_tech_structures)

            if len(enemy_tech_structures) > 2:
                self.has_published_scouted_enemy_tech_intel = True
                return True

        return False

    def scouted_enemy_proxy_hatchery(self):
        if not self.has_published_scouted_enemy_proxy_hatchery \
                and self.bot.build_manager.build_stage in {BuildStages.OPENING, BuildStages.EARLY_GAME}:

            # Enemy hatcheries on our side of the map
            nearby_enemy_hatcheries = self.bot.known_enemy_structures(const.UnitTypeId.HATCHERY).\
                closer_than(self.bot.start_location_to_enemy_start_location_distance / 2,
                            self.bot.start_location)

            # Enemy spine crawlers on our side of the map
            # Assume shenanigans.
            nearby_enemy_spines = self.bot.known_enemy_structures(const.UnitTypeId.SPINECRAWLER). \
                closer_than(self.bot.start_location_to_enemy_start_location_distance / 2,
                            self.bot.start_location)

            if nearby_enemy_hatcheries or nearby_enemy_spines:
                self.has_published_scouted_enemy_proxy_hatchery = True
                return True

        return False

    def scouted_greedy_early_opponent(self):
        if not self.has_published_scouted_greedy_early_opponent \
                and self.bot.build_manager.build_stage in {BuildStages.OPENING, BuildStages.EARLY_GAME}:

            # Enemy expansions excluding the starting location
            enemy_expansions = self.bot.known_enemy_units(const2.TOWNHALLS).further_than(
                11, self.bot.enemy_start_location).filter(lambda th: th.is_ready or th.build_progress > 0.8)

            if self.bot.enemy_race is sc2.Race.Terran:
                greedy_enough = len(enemy_expansions) > 0
            elif self.bot.enemy_race is sc2.Race.Zerg:
                greedy_enough = len(enemy_expansions) > 1
            elif self.bot.enemy_race is sc2.Race.Protoss:
                greedy_enough = len(enemy_expansions) > 0

            if greedy_enough:
                self.has_published_scouted_greedy_early_opponent = True
                return True

        return False

    def scouted_research_neural_parasite(self):
        if not self.has_published_research_neural_parasite:

            neural_parasite_targets = {
                const.COLOSSUS, const.CARRIER, const.MOTHERSHIP, const.ROBOTICSBAY,
                const.BATTLECRUISER,
            }
            enemy_tech_structures = self.bot.known_enemy_units(neural_parasite_targets)

            if len(enemy_tech_structures):
                self.has_published_research_neural_parasite = True
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
        if self.enemy_rush_scouted():
            self.publish(Messages.FOUND_ENEMY_RUSH)
        if self.enemy_worker_rush_scouted():
            self.publish(Messages.FOUND_ENEMY_WORKER_RUSH)
        if self.need_more_enemy_tech_intel():
            self.publish(Messages.NEED_MORE_ENEMY_TECH_INTEL)
        if self.scouted_enemy_tech_intel():
            self.publish(Messages.SCOUTED_ENOUGH_ENEMY_TECH_INTEL)
        if self.scouted_enemy_proxy_hatchery():
            self.publish(Messages.FOUND_ENEMY_PROXY_HATCHERY)
        if self.scouted_greedy_early_opponent():
            self.publish(Messages.FOUND_ENEMY_EARLY_GREED)
        if self.scouted_research_neural_parasite():
            self.publish(Messages.ALLOW_NEURAL_PARASITE_UPGRADE)

    async def run(self):
        await self.read_messages()
        await self.assess_game()


