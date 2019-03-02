import functools

import lib.sc2.constants as const

from lambdanaut import const2
from lambdanaut.const2 import Messages, DefenseStates
from lambdanaut.managers import StatefulManager


class DefenseManager(StatefulManager):
    """
    Class for handling base defense against enemy attacks
    """

    name = 'Defense Manager'

    def __init__(self, bot):
        super(DefenseManager, self).__init__(bot)

        # Default starting state
        self.state = DefenseStates.NOT_DEFENDING

        # The previous state
        self.previous_state = self.state

        # Map of functions to do depending on the state
        self.state_map = {
            DefenseStates.NOT_DEFENDING: self.do_not_defending,
            DefenseStates.DEFENDING: self.do_defending,
        }

        # Map of functions to do when entering the state
        self.state_start_map = {
        }

        # Map of functions to do when leaving the state
        self.state_stop_map = {
            DefenseStates.DEFENDING: self.stop_defending,
        }

        # Flag to set if we've published a message about defending against multiple
        # enemies since we last switched to the DEFENDING state
        self.published_defending_against_multiple_enemies = False

        # If this flag is false, we wont switch to DEFENDING state
        self.allow_defending = True

        # Subscribe to Messages
        self.subscribe(Messages.ALLOW_DEFENDING)
        self.subscribe(Messages.DONT_DEFEND)

    async def do_not_defending(self):
        pass

    async def do_defending(self):
        worker_non_targets = {const.BANELING, const.REAPER}
        defending_worker_min_health = 0.3

        for th in self.bot.townhalls:
            enemies_nearby = [u.snapshot for u in self.bot.enemy_cache.values()
                              if u.distance_to(th) < 45]

            if enemies_nearby:
                # Publish message if there are multiple enemies
                if not self.published_defending_against_multiple_enemies and \
                        len(enemies_nearby) > 4:
                    self.publish(Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES)
                    self.published_defending_against_multiple_enemies = True

                # Workers attack enemy
                ground_enemies = [enemy for enemy in enemies_nearby if not enemy.is_flying]
                workers = self.bot.workers.closer_than(14, th.position.closest(enemies_nearby).position)
                if ground_enemies and len(workers) > len(ground_enemies):
                    for worker in workers:
                        if worker.tag in self.bot.workers_defending:
                            target = self.bot.closest_and_most_damaged(ground_enemies, worker)
                            if target.type_id not in worker_non_targets:
                                self.bot.actions.append(worker.attack(target))

                        else:
                            # Add workers to defending workers and attack nearby enemy
                            # Use one more worker than there are enemies
                            # OR
                            # If the enemy is a single worker, just send one worker
                            if len(ground_enemies) == 1 and ground_enemies[0].type_id in const2.WORKERS:
                                defend_with_more_workers = len(self.bot.workers_defending) < 1
                            else:
                                defend_with_more_workers = len(self.bot.workers_defending) <= len(ground_enemies)

                            if defend_with_more_workers \
                                    and worker.health_percentage > defending_worker_min_health + 0.05:
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
                # 1-3 Enemies: 0.3 of map. 4 enemy: 0.4 of map. 5 enemy: 0.5 of map. 6 enemy: 0.6 of map...
                # 8 or more enemy: 0.8 of map
                distance_ratio_to_pull_back = max(0.3, min(0.8, len(enemies_nearby) * 0.1))
                army_clusters = \
                    [cluster for cluster in army_clusters
                     if th.distance_to(cluster.position) <
                     self.bot.start_location_to_enemy_start_location_distance * distance_ratio_to_pull_back]

                if army_clusters and self.bot.enemy_clusters:
                    nearest_enemy_cluster = th.position.closest(self.bot.enemy_clusters)
                    for army_cluster in army_clusters:
                        if army_cluster:
                            army_strength = self.bot.relative_army_strength(
                                army_cluster, nearest_enemy_cluster)

                            if army_strength >= -1 \
                                    or (army_strength > -6 and
                                        nearest_enemy_cluster.position.distance_to(army_cluster.position) < 15) \
                                    or self.bot.supply_used > 185:
                                # Attack enemy if we stand a chance or
                                # if we hardly stand a chance and they're in our face or
                                # if we're near supply max
                                for unit in army_cluster:
                                    if unit.type_id not in const2.NON_COMBATANTS \
                                            and unit.tag not in self.bot.townhall_queens.values():
                                        target = self.bot.closest_and_most_damaged(enemies_nearby, unit)

                                        if target and not self.bot.unit_is_busy(unit):
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
                                        towards_townhall = largest_army_cluster.position.towards(
                                            nearest_townhall, +2)
                                        self.bot.actions.append(unit.move(towards_townhall))

            # Bring back defending workers that have drifted too far from town halls
            workers_defending_to_remove = set()
            for worker_id in self.bot.workers_defending:
                worker = self.bot.workers.find_by_tag(worker_id)
                if worker:
                    townhalls = self.bot.townhalls.ready
                    if townhalls:
                        nearest_townhall = townhalls.closest_to(worker.position)

                        # Return hurt workers to working
                        if worker.health_percentage < defending_worker_min_health:
                            minerals = self.bot.state.mineral_field.closer_than(8, nearest_townhall)
                            if minerals:
                                workers_defending_to_remove.add(worker_id)
                                mineral = minerals.first
                                self.bot.actions.append(worker.gather(mineral))

                        # Return distant workers to working
                        elif worker.distance_to(nearest_townhall.position) > 18:
                            workers_defending_to_remove.add(worker_id)
                            self.bot.actions.append(worker.move(nearest_townhall.position))
                else:
                    workers_defending_to_remove.add(worker_id)

            # Remove workers from defending set
            self.bot.workers_defending -= workers_defending_to_remove

    async def stop_defending(self):
        # Cleanup workers that were defending and send them back to their townhalls
        townhalls = self.bot.townhalls.ready
        if townhalls:
            for worker in self.bot.workers:
                nearest_townhall = townhalls.closest_to(worker.position)

                if worker.tag in self.bot.workers_defending:
                    self.bot.actions.append(worker.move(nearest_townhall.position))
                elif worker.distance_to(nearest_townhall) > 14:
                    self.bot.actions.append(worker.move(nearest_townhall.position))

        self.bot.workers_defending.clear()  # Remove worker ids from set

        # Reset flag saying that we're defending against multiple enemies
        self.published_defending_against_multiple_enemies = False

    async def determine_state_change(self):
        for message, val in self.messages.items():
            if message in {Messages.ALLOW_DEFENDING}:
                self.ack(message)

                self.allow_defending = True

            elif message in {Messages.DONT_DEFEND}:
                self.ack(message)

                self.allow_defending = False

        # DEFENDING
        if self.state == DefenseStates.DEFENDING:
            # Loop through all townhalls. If enemies are near any of them, don't change state.
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    30, th.position).exclude_type(const2.ENEMY_NON_ARMY).filter(lambda u: u.is_visible)

                if enemies_nearby:
                    # Enemies found, don't change state.
                    break
            else:
                return await self.change_state(self.previous_state)

        # Switching to DEFENDING from any other state
        elif self.state != DefenseStates.DEFENDING and self.allow_defending:
            for th in self.bot.townhalls:
                enemies_nearby = self.bot.known_enemy_units.closer_than(
                    30, th).exclude_type(const2.ENEMY_NON_ARMY).filter(lambda u: u.is_visible)

                if enemies_nearby:
                    return await self.change_state(DefenseStates.DEFENDING)

    async def run(self):
        await super(DefenseManager, self).run()
