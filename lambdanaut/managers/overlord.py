import math

import lib.sc2.constants as const

import lambdanaut.const2 as const2
from lambdanaut.const2 import Messages, OverlordStates
from lambdanaut.expiringlist import ExpiringList
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
            OverlordStates.INITIAL_DIVE: self.start_initial_dive,
        }

        # Overlords used for scouting
        # These must be added to the set in scouting_overlord_tags()
        overlords = self.bot.units(const.OVERLORD)
        self.scouting_overlord_tag = overlords.first.tag if overlords else None
        self.proxy_scouting_overlord_tag = None
        self.third_expansion_scouting_overlord_tag = None
        self.baneling_drop_overlord_tag = None

        # Move second overlord to enemy ramp if this is true
        self.move_overlord_scout_2_to_enemy_ramp = False

        # Tags of overlords with creep turned on
        self.overlord_tags_with_creep_turned_on = set()

        # Message subscriptions
        self.subscribe(Messages.OVERLORD_SCOUT_2_TO_ENEMY_RAMP)
        self.subscribe(Messages.NEED_MORE_ENEMY_TECH_INTEL)
        self.subscribe(Messages.SCOUTED_ENOUGH_ENEMY_TECH_INTEL)

        # Expiring list of recent expansions we've sent an overlord to
        self._recent_expansions_visited = ExpiringList()

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

                self.move_overlord_scout_2_to_enemy_ramp = True
                if self.proxy_scouting_overlord_tag is not None:
                    overlords = self.bot.units(const.OVERLORD)
                    if overlords:
                        overlord = overlords.find_by_tag(self.proxy_scouting_overlord_tag)
                        if overlord:
                            self.move_overlord_to_enemy_ramp(overlord)

            # Change state to suicide dive
            change_state_to_suicide_dive = {
                Messages.NEED_MORE_ENEMY_TECH_INTEL}
            if message in change_state_to_suicide_dive:
                self.ack(message)
                await self.change_state(OverlordStates.SUICIDE_DIVE)

            # Change state to initial backout
            change_state_to_initial_backout = {
                Messages.SCOUTED_ENOUGH_ENEMY_TECH_INTEL}
            if message in change_state_to_initial_backout:
                self.ack(message)
                await self.change_state(OverlordStates.INITIAL_BACKOUT)

    def move_overlord_to_enemy_ramp(self, overlord):
        # Move them to the enemy ramp
        ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
        if ramps:
            nearby_ramp = self.bot.enemy_start_location.towards(
                self.bot.start_location, 2).closest(ramps)

            target = nearby_ramp.towards(self.bot.start_location, 9.5)
            self.bot.actions.append(overlord.move(target))

    def turn_on_generate_creep(self):
        # Spread creep on last scouted expansion location like a fucking dick head
        if self.bot.units({const.LAIR, const.HIVE}):
            overlords = self.bot.units(const.OVERLORD)
            if overlords:
                for overlord in overlords.filter(
                        lambda o: o.tag not in self.overlord_tags_with_creep_turned_on):
                    self.overlord_tags_with_creep_turned_on.add(overlord.tag)
                    self.bot.actions.append(
                        overlord(const.AbilityId.BEHAVIOR_GENERATECREEPON))

    def overlord_dispersal(self):
        """
        Disperse Overlords to different expansions
        """
        overlords = self.bot.units(const.OVERLORD).filter(
            lambda o: o.tag not in self.scouting_overlord_tags).idle

        if overlords:
            overlord = overlords.first

            # Get a list of expansion positions that
            # * We don't have overlords at already
            # * There aren't any enemies there
            # * And that we haven't visited recently
            if self.bot.enemy_cache:
                expansion_locations = [
                    expansion for expansion in self.bot.expansion_locations.keys()
                    if not self.bot.is_visible(expansion)
                    and expansion.distance_to_closest(self.bot.enemy_cache.values()) > 17
                    and expansion.distance_to_closest(overlords) > 16
                    and not self._recent_expansions_visited.contains(expansion, self.bot.state.game_loop)
                ]
            else:
                expansion_locations = []

            if expansion_locations:
                # There's an expansion location we aren't scouting. Check it out
                expansion = overlord.position.closest(expansion_locations)

                # Add expansion to expiring list so we don't check it again soon
                self._recent_expansions_visited.add(expansion, self.bot.state.game_loop, expiry=45)

                target = expansion.towards_with_random_angle(
                    self.bot.start_location, 9)
                self.bot.actions.append(overlord.move(target))

            else:
                # Just disperse randomly at angle around center of map
                distance = self.bot.start_location_to_enemy_start_location_distance * 0.5
                target = self.bot.start_location.towards_with_random_angle(
                    self.bot.enemy_start_location, distance, max_difference=(math.pi / 1.0))
                self.bot.actions.append(overlord.move(target))

    def proxy_scout_with_second_overlord(self):
        overlords = self.bot.units(const.OVERLORD)

        if self.proxy_scouting_overlord_tag is None and len(overlords) == 2:
            overlord = overlords.filter(lambda ov: ov.tag not in self.scouting_overlord_tags).first

            self.proxy_scouting_overlord_tag = overlord.tag

            if not self.move_overlord_scout_2_to_enemy_ramp:
                # Move Overlord around different expansion locations
                expansion_locations = self.bot.get_expansion_positions()
                if expansion_locations:
                    shortest_path = self.bot.shortest_path_between_points(expansion_locations[1:6])
                    for expansion_location in shortest_path:
                        self.bot.actions.append(overlord.move(expansion_location, queue=True))

                    try:
                        # This is the expected enemy 5th expand location
                        enemy_fifth_expansion = expansion_locations[-5]
                        self.bot.actions.append(overlord.move(enemy_fifth_expansion, queue=True))
                        self.bot.actions.append(overlord.stop(queue=True))
                    except IndexError:
                        # The indexed expansion doesn't exist
                        pass

        if overlords and self.proxy_scouting_overlord_tag is not None:
            scouting_overlord = overlords.find_by_tag(self.proxy_scouting_overlord_tag)
            if not scouting_overlord:
                # Overlord has died :(
                self.proxy_scouting_overlord_tag = None
                return

            if self.move_overlord_scout_2_to_enemy_ramp and scouting_overlord.is_idle:
                # Move the scouting overlord directly to the enemy ramp for vision
                self.move_overlord_to_enemy_ramp(scouting_overlord)

    def scout_enemy_third_expansion_with_third_overlord(self):
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

    def overlord_flee(self):
        """
        Flee overlords when they're near an enemy that can attack air
        """

        enemy_air_attacking_defensive_structures = {
            const.PHOTONCANNON,
            const.SPORECRAWLER,
            const.MISSILETURRET,
        }

        dont_flee_tags = {self.baneling_drop_overlord_tag}

        overlords = self.bot.units(const.OVERLORD).tags_not_in(dont_flee_tags)

        enemy_units = self.bot.enemy_cache.values()
        for overlord in overlords:
            nearby_enemy_units = [u.snapshot for u in enemy_units
                                  if u.can_attack_air
                                  and u.distance_to(overlord) < u.air_range * 1.5
                                  # For air-attacking static defense
                                  or (u.type_id in enemy_air_attacking_defensive_structures
                                      and u.distance_to(overlord) < u.air_range * 1.2)
                                  # For bunkers
                                  or (u.type_id is const.BUNKER and u.distance_to(overlord) < 9)
                                  ]

            if nearby_enemy_units:
                nearby_enemy_unit = overlord.position.closest(nearby_enemy_units)
                away_from_enemy = overlord.position.towards(nearby_enemy_unit, -3)
                self.bot.actions.append(overlord.move(away_from_enemy))

    def baneling_drops(self):
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

        # TODO: Test this to make sure it still works
        # Disable baneling drops for the time being
        return

        # Ensure we have Ventrical Sacks upgraded
        if const.OVERLORDSPEED in self.bot.state.upgrades \
                and self.bot.units(const.BANELINGNEST):
            # Get overlords
            overlords = self.bot.units(const.UnitTypeId.OVERLORD).ready. \
                tags_not_in(self.scouting_overlord_tags)
            overlord_transports = self.bot.units(const.UnitTypeId.OVERLORDTRANSPORT).ready. \
                tags_not_in(self.scouting_overlord_tags - {self.baneling_drop_overlord_tag})

            if self.baneling_drop_overlord_tag is None:
                if overlord_transports:
                    # Tag an overlord transport to drop with
                    self.print("Tagging overlord transport for a baneling drop")
                    overlord = overlord_transports.closest_to(self.bot.start_location)
                    self.baneling_drop_overlord_tag = overlord.tag
                elif overlords:
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
        # Early game scouting

        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord and overlord.is_idle:
            # Move towards natural expansion

            path = self.bot.shortest_path_to_enemy_start_location
            if path and len(path) > 10:
                # Move the overlord along the rush path a bit so we're more likely to see rushing zerglings
                index = round(len(path) * 0.7)
                point_along_path = path[index]
                self.bot.actions.append(overlord.move(point_along_path))

            self.bot.actions.append(overlord.move(enemy_natural_expansion, queue=True))

    async def do_initial_backout(self):
        """
        We've seen enemy structures
        Retreat from their natural expansion
        """
        enemy_natural_expansion = self.bot.get_enemy_natural_expansion()

        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord and overlord.is_idle:
            away_from_enemy_natural_expansion = \
                enemy_natural_expansion.position.towards(self.bot.start_location, +28)
            self.bot.actions.append(overlord.move(away_from_enemy_natural_expansion))

    async def do_suicide_dive(self):
        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord and overlord.is_idle:
            self.bot.actions.append(
                overlord.move(self.bot.enemy_start_location, queue=True))

    async def start_initial_dive(self):
        overlord = self.bot.units(const.OVERLORD).find_by_tag(self.scouting_overlord_tag)
        if overlord:
            self.bot.actions.append(
                overlord.move(self.bot.enemy_start_location.position))

    async def do_initial_dive(self):
        pass

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
                    if nearby_enemy_defensive_structures:
                        closest_enemy_defensive_structure = \
                            nearby_enemy_defensive_structures.closest_to(overlord)
                        self.publish(
                            Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                            value=closest_enemy_defensive_structure.position)

                        await self.change_state(OverlordStates.INITIAL_BACKOUT)

                if distance_to_expansion < 11:
                    if enemy_structures.closer_than(12, overlord) and \
                            self.bot.is_visible(enemy_natural_expansion):
                        # Check if they took their natural expansion
                        enemy_townhalls = enemy_structures.of_type(const2.TOWNHALLS)
                        if enemy_townhalls:
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
            pass

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
                    if nearby_enemy_defensive_structures:
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

                if enemy_structures.closer_than(11, overlord):
                    self.publish(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE, value=overlord.position)
                    await self.change_state(OverlordStates.INITIAL_BACKOUT)

                    enemy_townhalls = enemy_structures.of_type(const2.TOWNHALLS)
                    if enemy_townhalls:
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

        await self.read_messages()

        self.turn_on_generate_creep()
        self.proxy_scout_with_second_overlord()
        self.scout_enemy_third_expansion_with_third_overlord()
        self.baneling_drops()
        self.overlord_flee()
        self.overlord_dispersal()
