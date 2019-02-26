import functools
from typing import Callable, List

import lib.sc2.constants as const

from lambdanaut.builds import BuildStages
import lambdanaut.const2 as const2
from lambdanaut.expiringlist import ExpiringList
from lambdanaut.managers import Manager, StatefulManager
from lambdanaut.const2 import Messages, ForceManagerCommands, ForcesStates


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
            ForcesStates.DEFENDING: self.do_defending,
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
            ForcesStates.DEFENDING: self.stop_defending,
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

        # Flag to set if we've published a message about defending against multiple
        # enemies since we last switched to the DEFENDING state
        self.published_defending_against_multiple_enemies = False

        # Set of banelings attacking mineral lines
        self.banelings_harassing = set()

        # Set of roaches attacking mineral lines
        self.roaches_harassing = set()

        # If this flag is false, we wont switch to ATTACKING or MOVING_TO_ATTACK state
        self.allow_attacking = True

        # If this flag is false, we wont switch to ATTACKING_THROUGH_NYDUS
        # Is false by default
        self.allow_attacking_through_nydus = False

        # If this flag is false, we wont switch to DEFENDING state
        self.allow_defending = True

        # If this flag is set, don't stop attacking and don't change it to False until
        # self.dont_stop_attacking_condition returns True
        self.dont_stop_attacking = False
        self.dont_stop_attacking_condition: Callable[[Manager], bool] = None

        # Subscribe to messages
        self.subscribe(Messages.NEW_BUILD_STAGE)
        self.subscribe(Messages.DONT_STOP_ATTACKING_UNTIL_CONDITION)
        self.subscribe(Messages.ALLOW_DEFENDING)
        self.subscribe(Messages.DONT_ATTACK)
        self.subscribe(Messages.DONT_DEFEND)
        self.subscribe(Messages.ALLOW_ATTACKING_THROUGH_NYDUS)
        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
        self.subscribe(Messages.DRONE_LEAVING_TO_CREATE_HATCHERY)

    def get_army_value_to_attack(self, build_stage):
        """Given a build stage, returns the army value needed to begin an attack"""
        return {
            BuildStages.OPENING: 4,  # Assume rush. Attack with whatever we've got.
            BuildStages.EARLY_GAME: 25,  # Attack if we banked up some units early on
            BuildStages.MID_GAME: 55,  # Attack when a sizeable army is gained
            BuildStages.LATE_GAME: 73,  # Attack when a sizeable army is gained
        }[build_stage]

    def get_army_center_distance_to_attack(self, build_stage):
        """
        Based on the build stage, we may want to allow attacking when fewer or
        more units have met up at the moving_to_attack position.
        """
        return {
            BuildStages.OPENING: 60,  # Allow greater distances for rush
            BuildStages.EARLY_GAME: 5,
            BuildStages.MID_GAME: 5,
            BuildStages.LATE_GAME: 5,
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
        The point is 2/3rds the distance between our starting location and the target.
        """

        return target.towards(self.bot._game_info.map_center, +32)

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
            army_away_from_enemies = army.filter(
                lambda u: self.bot.known_enemy_units.closer_than(11, u) == 0)
            for unit in army_away_from_enemies:
                closest_townhall = townhalls.closest_to(unit)
                if closest_townhall.distance_to(unit) > 30:
                    self.bot.actions.append(unit.attack(closest_townhall.position))

            # Ensure each town hall has some army nearby
            closest_townhall = townhalls.closest_to(self.bot.enemy_start_location)
            for townhall in townhalls:

                number_of_units_to_townhall = round((len(army) / len(townhalls)) * 0.4)
                if townhall.tag == closest_townhall.tag:
                    # The closest townhall to the enemy should have more army
                    number_of_units_to_townhall = round((len(army) / len(townhalls)) * 3.5)

                nearby_army = army.closer_than(22, townhall.position)

                if len(nearby_army) < number_of_units_to_townhall:
                    # Move some army to this townhall
                    far_army = army.further_than(22, townhall.position)
                    if far_army:
                        unit = far_army.random
                        if not self.bot.known_enemy_units.closer_than(15, unit):
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
                        self.bot.actions.append(unit.attack(position))

    async def do_defending(self):
        """
        Defend townhalls from nearby enemies
        """

        worker_non_targets = {const.BANELING, const.REAPER}

        for th in self.bot.townhalls:
            enemies_nearby = [u.snapshot for u in self.bot.enemy_cache.values()
                              if u.distance_to(th) < 60]

            if enemies_nearby:
                # Publish message if there are multiple enemies
                if not self.published_defending_against_multiple_enemies and \
                        len(enemies_nearby) > 4:
                    self.publish(Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES)
                    self.published_defending_against_multiple_enemies = True

                # Workers attack enemy
                ground_enemies = [enemy for enemy in enemies_nearby if not enemy.is_flying]
                workers = self.bot.workers.closer_than(14, enemies_nearby[0].position)
                if ground_enemies and len(workers) > len(ground_enemies):
                    for worker in workers:
                        if worker.tag in self.bot.workers_defending:
                            target = self.bot.closest_and_most_damaged(ground_enemies, worker)
                            if target.type_id not in worker_non_targets:
                                self.bot.actions.append(worker.attack(target))

                        else:
                            # Add workers to defending workers and attack nearby enemy
                            if len(self.bot.workers_defending) <= len(ground_enemies):
                                target = self.bot.closest_and_most_damaged(ground_enemies, worker)
                                if target.type_id not in worker_non_targets:
                                    self.bot.workers_defending.add(worker.tag)
                                    self.bot.actions.append(worker.attack(target.position))
                else:
                    # If they have more than us, stop the worker from defending
                    for worker in workers:
                        if worker.tag in self.bot.workers_defending:
                            self.bot.workers_defending.remove(worker.tag)
                            self.bot.actions.append(worker.stop())

                # Have nearest queen defend
                queen_tag = self.bot.townhall_queens.get(th.tag)
                if queen_tag is not None:
                    queen = self.bot.units.find_by_tag(queen_tag)
                    if queen is not None and len(enemies_nearby) < 3:
                        # Only send the closest queen if the enemy is only a couple units
                        target = self.bot.closest_and_most_damaged(enemies_nearby, queen)

                        if target and 8 < queen.distance_to(target) < 15 and not queen.weapon_cooldown:
                            if target.distance_to(queen) < queen.ground_range:
                                self.bot.actions.append(queen.attack(target))
                            else:
                                self.bot.actions.append(queen.attack(target.position))
                        elif queen.distance_to(th) > 10:
                            self.bot.actions.append(queen.attack(th.position))

                # Have army clusters defend
                army_clusters = self.bot.army_clusters

                # The harder we're attacked, the further-out army to pull back
                # 1 Enemy: 0.05 of map. 2 enemy: 0.1 of map. 10 or more enemy: 1.0 of map
                distance_ratio_to_pull_back = max(1.0, len(enemies_nearby) * 0.05)
                if len(enemies_nearby) < 5:
                    army_clusters = \
                        [cluster for cluster in army_clusters
                         if self.bot.start_location.distance_to(cluster.position) <
                         self.bot.start_location_to_enemy_start_location_distance * distance_ratio_to_pull_back]

                if army_clusters:
                    nearest_enemy_cluster = self.bot.start_location.closest(self.bot.enemy_clusters)

                    if nearest_enemy_cluster:
                        for army_cluster in army_clusters:
                            if army_cluster:

                                army_strength = self.bot.relative_army_strength(
                                    army_cluster, nearest_enemy_cluster)

                                if army_strength >= -1 \
                                        or (army_strength > -6 and
                                            nearest_enemy_cluster.position.distance_to(army_cluster.position) < 10) \
                                        or self.bot.supply_used > 185:
                                    # Attack enemy if we stand a chance or
                                    # if we hardly stand a chance and they're in our face or
                                    # if we're near supply max
                                    for unit in army_cluster:
                                        if unit.type_id not in const2.NON_COMBATANTS \
                                                and unit.tag not in self.bot.townhall_queens.values():
                                            target = self.bot.closest_and_most_damaged(enemies_nearby, unit)

                                            if target and unit.weapon_cooldown <= 0 and not unit.is_attacking:
                                                self.bot.actions.append(unit.attack(target))

                                elif army_strength < -2:
                                    # If enemy is greater regroup to center of largest cluster towards friendly townhall
                                    largest_army_cluster = functools.reduce(
                                        lambda c1, c2: c1 if len(c1) >= len(c2) else c2,
                                        army_clusters[1:],
                                        army_clusters[0])

                                    for unit in army_cluster:
                                        if unit.type_id not in const2.NON_COMBATANTS:
                                            nearest_townhall = self.bot.townhalls.closest_to(unit.position)
                                            if unit.distance_to(nearest_townhall) > 6:
                                                towards_townhall = largest_army_cluster.position.towards(nearest_townhall, +2)
                                                self.bot.actions.append(unit.move(towards_townhall))

            # Bring back defending workers that have drifted too far from town halls
            workers_defending_to_remove = set()
            for worker_id in self.bot.workers_defending:
                worker = self.bot.workers.find_by_tag(worker_id)
                if worker:
                    townhalls = self.bot.townhalls.ready
                    if townhalls:
                        nearest_townhall = townhalls.closest_to(worker.position)
                        if worker.distance_to(nearest_townhall.position) > 18:
                            workers_defending_to_remove.add(worker_id)
                            self.bot.actions.append(worker.move(nearest_townhall.position))
                else:
                    workers_defending_to_remove.add(worker_id)

            # Remove workers from defending set
            self.bot.workers_defending -= workers_defending_to_remove

    async def stop_defending(self):
        # Cleanup workers that were defending and send them back to their townhalls
        for worker in self.bot.workers:
            nearest_townhall = self.bot.townhalls.ready.closest_to(worker.position)

            if worker.tag in self.bot.workers_defending:
                self.bot.actions.append(worker.move(nearest_townhall.position))
            elif worker.distance_to(nearest_townhall) > 14:
                self.bot.actions.append(worker.move(nearest_townhall.position))

        self.bot.workers_defending.clear()  # Remove worker ids from set

        # Reset flag saying that we're defending against multiple enemies
        self.published_defending_against_multiple_enemies = False

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
            if not unit.is_attacking and not unit.is_moving:
                self.bot.actions.append(unit.attack(nearby_target))

    async def start_attacking(self):
        # Command for when attacking starts
        self._recent_commands.add(ForceManagerCommands.START_ATTACKING, self.bot.state.game_loop, expiry=4)

        # Do Baneling harass during attack
        banelings = self.bot.units(const.BANELING) \
            .tags_not_in(self.bot.occupied_units)
        if banelings:
            # Take 4 banelings if we have 4, otherwise just don't harass
            # This returns a list (not a Units Group)
            try:
                harass_banelings: List = banelings.take(4)
            except AssertionError:
                # Backwards compatibility with older python-sc2 versions
                harass_banelings = []
            if harass_banelings:
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

                        for baneling in harass_banelings:
                            target = enemy_townhall
                            self.bot.actions.append(baneling.move(target.position))
                            self.banelings_harassing.add(baneling.tag)

            # Burrow banelings
            burrowed_banelings = self.bot.units(const.BANELINGBURROWED)
            # Only burrow up to six banelings at a time
            if const.BURROW in self.bot.state.upgrades and \
                    (not burrowed_banelings or len(burrowed_banelings) < 4):
                # Get the banelings that aren't harassing mineral lines
                banelings = banelings.tags_not_in(self.banelings_harassing)

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
                if not unit.is_attacking and not unit.is_moving and unit.weapon_cooldown <= 0:
                    self.bot.actions.append(unit.attack(target))

        # Send in the frontline army immediatelly
        for unit in frontline_army:
            if not unit.is_attacking and not unit.is_moving and unit.weapon_cooldown <= 0:
                self.bot.actions.append(unit.attack(target))

    async def do_attacking_through_nydus(self):
        pass

    async def start_retreating(self):
        # Add START_RETREATING to recent commands so we don't switch states for a bit.
        self._recent_commands.add(ForceManagerCommands.START_RETREATING,
                                  self.bot.state.game_loop, expiry=50)

    async def do_retreating(self):
        army = self.bot.units(const2.ZERG_ARMY_UNITS). \
            tags_not_in(self.bot.occupied_units)

        for unit in army:
            if unit.weapon_cooldown or unit.is_idle or unit.is_moving:
                townhalls = self.bot.townhalls
                if townhalls:
                    nearest_townhall = townhalls.closest_to(unit)
                    self.bot.actions.append(unit.move(nearest_townhall))

    async def do_searching(self):
        army = self.bot.units(const2.ZERG_ARMY_UNITS).\
            tags_not_in(self.bot.occupied_units).idle

        if not army:
            return

        # Get expansion locations starting from enemy start location
        enemy_expansion_positions = self.bot.get_enemy_expansion_positions()

        for expansion in enemy_expansion_positions:
            for unit in army:
                self.bot.actions.append(unit.move(expansion, queue=True))

    async def determine_state_change(self):
        # Reacting to subscribed messages
        for message, val in self.messages.items():
            # Start searching for an enemy location if we can't find it
            if message in {Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION}:
                if self.state != ForcesStates.DEFENDING:
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

            elif message in {Messages.ALLOW_DEFENDING}:
                self.ack(message)

                self.allow_defending = True

            elif message in {Messages.DONT_DEFEND}:
                self.ack(message)

                self.allow_defending = False

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
                        and ((relative_army_strength > 9 and len(army) > 4)
                             or army_value > self.army_value_to_attack):
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
                if escorting_worker.distance_to(expansion_location) < 1:
                    return await self.change_state(ForcesStates.HOUSEKEEPING)

        # DEFENDING
        elif self.state == ForcesStates.DEFENDING:
            # Loop through all townhalls. If enemies are near any of them, don't change state.
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    23, th.position).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby:
                    # Enemies found, don't change state.
                    break
            else:
                units_attacking = self.bot.units.filter(lambda u: u.is_attacking and not u.is_moving)

                # If none of our units are still attacking, change state
                if not units_attacking:
                    return await self.change_state(self.previous_state)

        # MOVING_TO_ATTACK
        elif self.state == ForcesStates.MOVING_TO_ATTACK:
            army = self.bot.units(const2.ZERG_ARMY_UNITS)

            if army:
                relative_army_strength = self.bot.relative_army_strength(
                    army, self.bot.enemy_cache.values(), ignore_workers=True)

                # If we're allowed to stop attacking
                if not self.dont_stop_attacking:
                    # Switch back to housekeeping if our army is weaker and we're not max supply
                    if relative_army_strength < -5 and self.bot.supply_used < 180:
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
                    # Value of the army
                    army_value = sum(const2.ZERG_ARMY_VALUE[unit.type_id] for unit in army)

                    if army_value < self.army_value_to_attack * 0.4:
                        return await self.change_state(ForcesStates.HOUSEKEEPING)

                    # Retreat if our entire army is weaker than the army we see from them and we're not near max
                    enemy = self.bot.known_enemy_units.exclude_type(const2.WORKERS).not_structure
                    if enemy:
                        relative_army_strength = self.bot.relative_army_strength(army, enemy, ignore_workers=True)
                        if relative_army_strength < -3 and self.bot.supply_used < 170:
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

        # Switching to DEFENDING from any other state
        if self.state != ForcesStates.DEFENDING and self.allow_defending:
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    23, th).exclude_type(const2.ENEMY_NON_ARMY)

                if enemies_nearby:
                    return await self.change_state(ForcesStates.DEFENDING)

        # If self.dont_stop_attacking is set, then
        # Check if we're ready to allow attacking again
        if self.dont_stop_attacking and self.dont_stop_attacking_condition is not None:
            if self.dont_stop_attacking_condition(self):
                self.dont_stop_attacking = False
                self.dont_stop_attacking_condition = None

    async def run(self):
        await super(ForceManager, self).run()

        await self.update_enemy_army_position()


