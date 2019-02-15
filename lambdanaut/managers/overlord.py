import math

import sc2.constants as const

import lambdanaut.const2 as const2
from lambdanaut.const2 import Messages, OverlordStates
from lambdanaut.managers import StatefulManager
import lambdanaut.utils as utils


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
                nearby_enemy_units = self.bot.units.enemy. \
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
            overlords = self.bot.units(const.UnitTypeId.OVERLORD).ready. \
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
                    enemy_targets = self.bot.known_enemy_units.of_type(enemy_priorities). \
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
