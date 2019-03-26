from typing import Callable, List

import lib.sc2.constants as const

from lambdanaut.builds import BuildStages
import lambdanaut.const2 as const2
from lambdanaut.expiringlist import ExpiringList
from lambdanaut.managers import Manager, StatefulManager
from lambdanaut.const2 import DefenseStates, ForceManagerCommands, ForcesStates, Messages


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
            ForcesStates.MOVING_TO_ATTACK: self.do_moving_to_attack,
            ForcesStates.ATTACKING: self.do_attacking,
            ForcesStates.ATTACKING_THROUGH_NYDUS: self.do_attacking_through_nydus,
            ForcesStates.RETREATING: self.do_retreating,
            ForcesStates.SEARCHING: self.do_searching,
        }

        # Map of functions to do when entering the state
        self.state_start_map = {
            ForcesStates.ATTACKING: self.start_attacking,
            ForcesStates.RETREATING: self.start_retreating,
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
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

        # Set of banelings attacking mineral lines
        self.banelings_harassing = set()

        # Set of roaches attacking mineral lines
        self.roaches_harassing = set()

        # If this flag is false, we wont switch to ATTACKING or MOVING_TO_ATTACK state
        self.allow_attacking = True

        # If this flag is false, we wont switch to ATTACKING_THROUGH_NYDUS
        # Is false by default
        self.allow_attacking_through_nydus = False

        # If this flag is set, don't stop attacking and don't change it to False until
        # self.dont_stop_attacking_condition returns True
        self.dont_stop_attacking = False
        self.dont_stop_attacking_condition: Callable[[Manager], bool] = None

        # Subscribe to messages
        self.subscribe(Messages.NEW_BUILD_STAGE)
        self.subscribe(Messages.STATE_ENTERED)
        self.subscribe(Messages.DONT_STOP_ATTACKING_UNTIL_CONDITION)
        self.subscribe(Messages.DONT_ATTACK)
        self.subscribe(Messages.ALLOW_ATTACKING_THROUGH_NYDUS)
        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
        self.subscribe(Messages.DRONE_LEAVING_TO_CREATE_HATCHERY)

    def get_army_value_to_attack(self, build_stage):
        """Given a build stage, returns the army value needed to begin an attack"""
        return {
            BuildStages.OPENING: 3,  # Assume rush. Attack with whatever we've got.
            BuildStages.EARLY_GAME: 45,  # Attack if we banked up some units early on
            BuildStages.MID_GAME: 60,  # Attack when a sizeable army is gained
            BuildStages.LATE_GAME: 75,  # Attack when a sizeable army is gained
        }[build_stage]

    def get_army_center_distance_to_attack(self, build_stage):
        """
        Based on the build stage, we may want to allow attacking when fewer or
        more units have met up at the moving_to_attack position.
        """
        return {
            BuildStages.OPENING: 60,  # Allow greater distances for rush
            BuildStages.EARLY_GAME: 8,
            BuildStages.MID_GAME: 11,
            BuildStages.LATE_GAME: 14,
        }[build_stage]

    def get_target(self):
        """Returns enemy target to move nearby during moving_to_attack"""
        enemy_structures = self.bot.known_enemy_structures

        # Get target to attack towards
        if self.last_enemy_army_position is not None:
            # Use the location of the last seen enemy army, and group up away from that position
            target = self.last_enemy_army_position
        elif enemy_structures:
            # Use enemy structure
            target = enemy_structures.closest_to(self.bot.start_location).position
        else:
            # Use enemy start location
            target = self.bot.enemy_start_location.position

        return target

    def get_nearby_to_target(self, target):
        """
        Gets a point nearby the target.
        """

        if target.distance_to(self.bot.start_location) < self.bot.start_location_to_enemy_start_location_distance / 2:
            # If the target is on our side of the map, group up towards our start location
            nearby_target = target.towards(self.bot.start_location, +32)
        else:
            # If the target is on their side of the map, group up towards the center of the map
            nearby_target = target.towards(self.bot._game_info.map_center, +32)

        return nearby_target

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
        zerg_army_units = const2.ZERG_ARMY_UNITS | {const.ROACHBURROWED, const.INFESTORBURROWED}

        army = self.bot.units(zerg_army_units).tags_not_in(self.bot.occupied_units)

        # Army includes queens that aren't busy
        busy_queen_tags = self.bot.townhall_queens.values()
        queens = self.bot.units(const.QUEEN).filter(
            lambda q: q.tag not in busy_queen_tags)
        army |= queens

        townhalls = self.bot.townhalls

        if townhalls:
            # Call back army that is far away if they don't have nearby enemies
            for unit in army:
                if not self.bot.unit_is_busy(unit):
                    closest_townhall = townhalls.closest_to(unit)
                    if closest_townhall.distance_to(unit) > 35:
                        self.bot.actions.append(unit.attack(closest_townhall.position))

            # Ensure each town hall has some army nearby
            closest_townhall = townhalls.closest_to(self.bot.enemy_start_location)
            for townhall in townhalls:

                number_of_units_to_townhall = round((len(army) / len(townhalls)) * 0.4)
                if townhall.tag == closest_townhall.tag:
                    # The closest townhall to the enemy should have more army
                    number_of_units_to_townhall = round((len(army) / len(townhalls)) * 3)

                nearby_army = army.closer_than(22, townhall.position)

                if len(nearby_army) < number_of_units_to_townhall:
                    # Move some army to this townhall
                    far_army = army.further_than(22, townhall.position)
                    if far_army:
                        unit = far_army.random
                        if unit.is_idle:
                            # Move them to the nearest ramp
                            target = townhall.position

                            nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                            nearby_ramp = target.towards(self.bot.enemy_start_location, 4). \
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
                    army = self.bot.units(const2.ZERG_ARMY_UNITS). \
                        tags_not_in(self.bot.occupied_units)
                    expansion_location = await self.bot.get_next_expansion()

                    # Move with worker until we get up to the expansion
                    if escorting_worker.distance_to(expansion_location) > 12:
                        position = escorting_worker.position

                    else:
                        towards_enemy = expansion_location.towards(self.bot.enemy_start_location, +8)
                        position = towards_enemy

                    for unit in army:
                        if not self.bot.unit_is_busy(unit):
                            self.bot.actions.append(unit.attack(position))

    async def do_moving_to_attack(self):
        army_units = const2.ZERG_ARMY_UNITS

        army = self.bot.units(army_units). \
            tags_not_in(self.bot.occupied_units)

        if not army:
            return

        main_target = self.get_target()

        # Get target to attack towards
        nearby_target = self.get_nearby_to_target(main_target)

        # Search for another spot to move to
        # if not self.bot.in_pathing_grid(nearby_target):
        nearby_target = self.bot.find_nearby_pathable_point(nearby_target)

        for unit in army:
            if not self.bot.unit_is_busy(unit):
                self.bot.actions.append(unit.attack(nearby_target))

    async def start_attacking(self):
        # Command for when attacking starts
        self._recent_commands.add(ForceManagerCommands.START_ATTACKING, self.bot.state.game_loop, expiry=4)

        # Do Baneling harass during attack
        banelings = self.bot.units(const.BANELING) \
            .tags_not_in(self.bot.occupied_units)
        if banelings:

            # Split off 4 banelings to attack another townhall.
            # TAKEN OUT BECAUSE BANELINGS WOULDN'T TURN AROUND AFTER BEING SENT ON THEIR WAY

            # Take 4 banelings if we have 4, otherwise just don't harass
            # This returns a list (not a Units Group)
            # try:
            #     harass_banelings: List = banelings.take(4)
            # except AssertionError:
            #     # Backwards compatibility with older python-sc2 versions
            #     harass_banelings = []
            # if harass_banelings:
            #     enemy_structures = self.bot.known_enemy_structures
            #
            #     if enemy_structures:
            #         # Get expansion locations starting from enemy start location
            #         enemy_townhalls = enemy_structures.of_type(
            #             const2.TOWNHALLS)
            #
            #         if enemy_townhalls:
            #             # Get the enemy townhall that we know of that is the furthest away from
            #             # the closest enemy structure we know of. Hopefully this means they attack
            #             # far away from where the main army will be attacking
            #             enemy_townhall = enemy_townhalls.furthest_to(
            #                 enemy_structures.closest_to(self.bot.start_location))
            #
            #             for baneling in harass_banelings:
            #                 target = enemy_townhall
            #                 self.bot.actions.append(baneling.move(target.position))
            #                 self.banelings_harassing.add(baneling.tag)

            # Burrow banelings
            burrowed_banelings = self.bot.units(const.BANELINGBURROWED)
            # Only burrow up to six banelings at a time
            if const.BURROW in self.bot.state.upgrades and \
                    (not burrowed_banelings or len(burrowed_banelings) < 4):

                # Get the banelings that aren't harassing mineral lines
                banelings = banelings.tags_not_in(self.banelings_harassing).sorted(
                    lambda b: b.distance_to(self.bot.enemy_start_location))

                if len(banelings) >= 4:
                    # Get two banelings
                    banelings = banelings[:2]

                    army = self.bot.units(const2.ZERG_ARMY_UNITS)
                    if army:
                        for baneling in banelings:
                            # Consider them harassing banelings for the moment
                            self.banelings_harassing.add(baneling.tag)

                            # Move them to the nearest point along the shortest path to the
                            # enemy main and burrow them
                            path = self.bot.shortest_path_to_enemy_start_location

                            if path:
                                target = baneling.position.closest(path)
                            else:
                                target = army.center

                            self.bot.actions.append(baneling.move(target))
                            self.bot.actions.append(
                                baneling(const.AbilityId.BURROWDOWN_BANELING, queue=True))

        # Do burrow roach harass during attack
        roaches = self.bot.units(const.ROACH)
        if roaches and const.BURROW in self.bot.state.upgrades and \
                const.UpgradeId.TUNNELINGCLAWS in self.bot.state.upgrades:
            # Get the roaches that aren't harassing mineral lines
            roaches = roaches.tags_not_in(self.roaches_harassing)

            if len(roaches) >= 4:
                # Get two roaches
                roaches = roaches[:2]

                enemy_structures = self.bot.known_enemy_structures
                if enemy_structures:
                    # Get expansion locations starting from enemy start location
                    enemy_townhalls = enemy_structures.of_type(
                        const2.TOWNHALLS)

                    if enemy_townhalls:
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
        if mutalisks:
            dangerous_enemy_units = {const.PHOTONCANNON, const.SPORECRAWLER, const.MISSILETURRET}

            enemy_structures = self.bot.known_enemy_structures

            if enemy_structures:
                # Get expansion locations starting from enemy start location
                enemy_townhalls = enemy_structures.of_type(
                    const2.TOWNHALLS).filter(
                    lambda th: enemy_structures.of_type(
                        dangerous_enemy_units).closer_than(7, th).empty)

                if enemy_townhalls:
                    for mutalisk in mutalisks:
                        enemy_expansion = enemy_townhalls.random
                        self.bot.actions.append(mutalisk.move(enemy_expansion))
                else:
                    for mutalisk in mutalisks:
                        target = enemy_structures.random.position
                        self.bot.actions.append(mutalisk.move(target))

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
        army = self.bot.units(const2.ZERG_ARMY_UNITS). \
            exclude_type(no_attackmove_units). \
            tags_not_in(self.bot.occupied_units)

        # Exclude the banelings that are currently harassing
        army -= self.bot.units.tags_in(self.banelings_harassing)

        backline_army = army.exclude_type(frontline_army_units)
        frontline_army = army.of_type(frontline_army_units)

        if not army:
            return

        enemy_structures = self.bot.known_enemy_structures

        # Prefer not flying enemy structures so our ground units aren't confused
        # by flying terran structures
        not_flying_enemy_structures = enemy_structures.not_flying
        if not_flying_enemy_structures:
            enemy_structures = not_flying_enemy_structures

        if enemy_structures:
            target = enemy_structures.closest_to(army.center).position
        else:
            target = self.bot.enemy_start_location

        # Hold back the backline army for a few seconds
        if not self._recent_commands.contains(
                ForceManagerCommands.START_ATTACKING, self.bot.state.game_loop):
            for unit in backline_army:
                if not self.bot.unit_is_busy(unit):
                    self.bot.actions.append(unit.attack(target))

        # Send in the frontline army immediatelly
        for unit in frontline_army:
            if not self.bot.unit_is_busy(unit):
                self.bot.actions.append(unit.attack(target))

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

    async def do_attacking_through_nydus(self):
        pass

    async def start_retreating(self):
        # Add START_RETREATING to recent commands so we don't switch states for a bit.
        self._recent_commands.add(ForceManagerCommands.START_RETREATING,
                                  self.bot.state.game_loop, expiry=20)

    async def do_retreating(self):
        army = self.bot.units(const2.ZERG_ARMY_UNITS). \
            tags_not_in(self.bot.occupied_units)

        for unit in army:
            if not self.bot.unit_is_engaged(unit):
                townhalls = self.bot.townhalls
                if townhalls:
                    nearest_townhall = townhalls.closest_to(unit)
                    if nearest_townhall.distance_to(unit) > 20:
                        self.bot.actions.append(unit.move(nearest_townhall.position))

    async def do_searching(self):
        army = self.bot.units(const2.ZERG_ARMY_UNITS).\
            tags_not_in(self.bot.occupied_units).idle

        if not army:
            return

        # Get expansion locations starting from enemy start location
        enemy_expansion_positions = self.bot.get_enemy_expansion_positions()

        for expansion in enemy_expansion_positions:
            for unit in army:
                if not self.bot.unit_is_busy(unit):
                    self.bot.actions.append(unit.attack(expansion, queue=True))

    async def determine_state_change(self):
        # Reacting to subscribed messages
        for message, val in self.messages.items():
            # Start searching for an enemy location if we can't find it
            if message in {Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION}:
                self.ack(message)
                return await self.change_state(ForcesStates.SEARCHING)

            elif message in {Messages.DRONE_LEAVING_TO_CREATE_HATCHERY}:
                self.ack(message)
                if self.state == ForcesStates.HOUSEKEEPING:

                    # Add the escorted worker to a list for 25 seconds
                    self.escorting_workers.add(val, iteration=self.bot.state.game_loop, expiry=25)

                    return await self.change_state(ForcesStates.ESCORTING)

            elif message in {Messages.NEW_BUILD_STAGE}:
                self.ack(message)

                # Update army value required to attack
                new_army_value_to_attack = self.get_army_value_to_attack(val)
                self.army_value_to_attack = new_army_value_to_attack
                self.print("New army value to attack with: {}".format(
                    new_army_value_to_attack))

                # Update distance to moving_to_attack meetup center required to attack
                new_distance_to_moving_to_attack = self.get_army_center_distance_to_attack(val)
                self.distance_to_moving_to_attack = new_distance_to_moving_to_attack

            elif message in {Messages.STATE_ENTERED}:
                self.ack(message)

                if val is DefenseStates.DEFENDING:
                    if self.state is ForcesStates.RETREATING:
                        # Return to housekeeping if we're retreating and we start defending
                        return await self.change_state(ForcesStates.HOUSEKEEPING)

            elif message in {Messages.DONT_ATTACK}:
                self.ack(message)

                self.allow_attacking = False

                if self.state in {ForcesStates.ATTACKING, ForcesStates.MOVING_TO_ATTACK}:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

            elif message in {Messages.DONT_STOP_ATTACKING_UNTIL_CONDITION}:
                self.ack(message)

                self.dont_stop_attacking = True
                self.dont_stop_attacking_condition = val

        # HOUSEKEEPING
        if self.state == ForcesStates.HOUSEKEEPING:

            army = self.bot.units(const2.ZERG_ARMY_UNITS)

            if army:
                # Value of the army
                army_value = sum(const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army)

                relative_army_strength = self.bot.relative_army_strength(
                    army, self.bot.enemy_cache.values(), ignore_workers=True)

                if self.allow_attacking \
                        and ((relative_army_strength > 6 and len(army) > 6)
                             or (relative_army_strength > -4
                                 and army_value > self.army_value_to_attack)) \
                             or self.bot.supply_used > 195:
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
                if expansion_location and escorting_worker.distance_to(expansion_location) < 1:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

        # MOVING_TO_ATTACK
        elif self.state == ForcesStates.MOVING_TO_ATTACK:
            army = self.bot.units(const2.ZERG_ARMY_UNITS)

            if army:
                relative_army_strength = self.bot.relative_army_strength(
                    army, self.bot.enemy_cache.values(), ignore_workers=True)

                # If we're allowed to stop attacking
                if not self.dont_stop_attacking:
                    # Switch back to housekeeping if our army is weaker and we're not max supply
                    if relative_army_strength < -2 and self.bot.supply_used < 180:
                        return await self.change_state(ForcesStates.HOUSEKEEPING)

                # Start attacking when army has amassed
                target = self.get_target()
                nearby_target = self.get_nearby_to_target(target)
                if army.center.distance_to(nearby_target) < self.distance_to_moving_to_attack:
                    return await self.change_state(ForcesStates.ATTACKING)

        # ATTACKING
        elif self.state == ForcesStates.ATTACKING:
            army = self.bot.units(const2.ZERG_ARMY_UNITS)

            if army:

                # If we're allowed to stop attacking
                if not self.dont_stop_attacking:
                    # Retreat if our entire army is weaker than the army we see from them and we're not near max
                    relative_army_strength = self.bot.relative_army_strength(
                        army, self.bot.enemy_cache.values(), ignore_workers=True)

                    if (relative_army_strength < -2) \
                            and self.bot.supply_used < 170:
                        return await self.change_state(ForcesStates.RETREATING)

                enemy_start_location = self.bot.enemy_start_location.position
                # Start searching the map if we're at the enemy's base and can't find them.
                if army.center.distance_to(enemy_start_location) < 25 and \
                        not self.bot.known_enemy_structures:

                    self.publish(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)

                    return await self.change_state(ForcesStates.SEARCHING)

        # RETREATING
        elif self.state == ForcesStates.RETREATING:
            if not self._recent_commands.contains(
                    ForceManagerCommands.START_RETREATING, self.bot.state.game_loop):
                return await self.change_state(ForcesStates.HOUSEKEEPING)

        # SEARCHING
        elif self.state == ForcesStates.SEARCHING:
            enemy_structures = self.bot.known_enemy_structures
            if enemy_structures:
                self.publish(Messages.ARMY_FOUND_ENEMY_BASE, value=enemy_structures.first.position)
                return await self.change_state(ForcesStates.HOUSEKEEPING)

            units_at_enemy_location = self.bot.units.closer_than(
                6, self.bot.enemy_start_location)

            if units_at_enemy_location:
                self.publish(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)

        # If self.dont_stop_attacking is set, then
        # Check if we're ready to allow attacking again
        if self.dont_stop_attacking and self.dont_stop_attacking_condition is not None:
            if self.dont_stop_attacking_condition(self):
                self.dont_stop_attacking = False
                self.dont_stop_attacking_condition = None

    async def run(self):
        await super(ForceManager, self).run()

        await self.update_enemy_army_position()


