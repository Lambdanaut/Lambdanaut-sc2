import math
import random
from typing import Optional

from lib.sc2.position import Point2
from lib.sc2.units import Units
import lib.sc2.constants as const

from lambdanaut.builds import Builds
from lambdanaut.expiringlist import ExpiringList
from lambdanaut.const2 import Messages, ResourceManagerCommands
from lambdanaut.managers import Manager


class ResourceManager(Manager):
    """
    Class for handling resource management. Involves:

    * Worker harvester management
    * Queen injection
    * Queen creep spread
    * Tumor creep spread
    """

    name = 'Resource Manager'

    def __init__(self, bot):
        super(ResourceManager, self).__init__(bot)

        self._recent_commands = ExpiringList()

        # Sets the number of workers to mine vespene gas per geyser
        self._ideal_vespene_worker_count: Optional[int] = None

        # Message subscriptions
        self.subscribe(Messages.NEW_BUILD)
        self.subscribe(Messages.UPGRADE_STARTED)
        self.subscribe(Messages.PULL_WORKERS_OFF_VESPENE)
        self.subscribe(Messages.PULL_WORKERS_OFF_VESPENE_FOR_X_SECONDS)
        self.subscribe(Messages.CLEAR_PULLING_WORKERS_OFF_VESPENE)
        self.subscribe(Messages.DONT_RETURN_DISTANT_WORKERS_TO_TOWNHALLS)

        self.allow_return_distant_workers_to_townhalls = True

        # If this flag is set, pull off gas when zergling speed is researched
        self.pull_off_gas_early = True

    async def init(self):
        # Send all workers to the closest mineral patch
        self.initialize_workers()

    def initialize_workers(self):
        minerals = self.bot.mineral_field
        for worker in self.bot.workers:
            mineral = minerals.closest_to(worker)
            self.bot.do(worker.gather(mineral))

    def get_untargeted_minerals(self, minerals: Units):
        """
        Filters a unit group of minerals for minerals that are not targeted by a worker

        If all of the minerals are targeted, return all minerals on map.
        """
        workers = self.bot.workers.collecting

        targeted_mineral_tags = set()

        for worker in workers:
            if isinstance(worker.order_target, int):
                targeted_mineral_tags.add(worker.order_target)

        untargeted_minerals = minerals.tags_not_in(targeted_mineral_tags)

        if untargeted_minerals:
            return untargeted_minerals
        else:
            return self.bot.mineral_field

    def return_distant_workers_to_townhalls(self):
        if self.allow_return_distant_workers_to_townhalls:
            townhalls = self.bot.townhalls
            if townhalls:
                for worker in self.bot.workers:
                    closest_townhall = townhalls.closest_to(worker)
                    if closest_townhall.distance_to(worker) > 50:
                        minerals = self.bot.mineral_field
                        if minerals:
                            mineral = self.bot.mineral_field.closest_to(closest_townhall)
                            self.bot.do(worker.gather(mineral))

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

        # Unsaturated Townhalls include townhalls that are almost complete
        unsaturated_townhalls = self.bot.townhalls.filter(
            lambda th: th.assigned_harvesters < th.ideal_harvesters or
                       (not th.is_ready and th.build_progress > 0.88))

        if not unsaturated_townhalls:
            return

        # Move excess worker off saturated minerals to unsaturated minerals
        for saturated_townhall in saturated_townhalls:
            mineral_workers = self.bot.workers.filter(
                lambda worker: worker.is_carrying_minerals and worker.is_collecting)
            if mineral_workers:
                worker = mineral_workers.closest_to(saturated_townhall)
                unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
                minerals = self.get_untargeted_minerals(
                    self.bot.mineral_field.closer_than(9, unsaturated_townhall))
                mineral = minerals.closest_to(unsaturated_townhall)

                self.bot.do(worker.return_resource(unsaturated_townhall))
                self.bot.do(worker.gather(mineral, queue=True))

    async def manage_minerals(self):
        await self.manage_mineral_saturation()

        # Move idle workers to mining
        for worker in self.bot.workers.idle:
            townhalls = self.bot.townhalls.ready

            if townhalls:
                townhall = townhalls.closest_to(worker)
                minerals = self.get_untargeted_minerals(
                    self.bot.mineral_field.closer_than(9, townhall))
                mineral = minerals.closest_to(townhall)

                if worker.is_carrying_minerals or worker.is_carrying_vespene:
                    self.bot.do(worker.return_resource(townhall))
                    self.bot.do(worker.gather(mineral, queue=True))
                else:
                    self.bot.do(worker.gather(mineral))

    async def manage_vespene(self):
        # If we have over 10 times the vespene than we do minerals, hold off on gas
        if self.bot.vespene > 500 and self.bot.minerals > 50 \
                and self.bot.vespene / self.bot.minerals > 10 and \
                not self._recent_commands.contains(
                    ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                    self.bot.state.game_loop):

            self._recent_commands.add(
                ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                self.bot.state.game_loop, expiry=25)

        saturated_extractors = self.bot._units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters > (self._ideal_vespene_worker_count or extr.ideal_harvesters)).ready

        unsaturated_extractors = self.bot._units(const.EXTRACTOR).filter(
            lambda extr: extr.assigned_harvesters < (self._ideal_vespene_worker_count or extr.ideal_harvesters)).ready

        if self._recent_commands.contains(
                ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE, self.bot.state.game_loop):
            # We're currently pulling workers off of vespene gas
            vespene_workers = self.bot.workers.filter(
                lambda worker: worker.is_carrying_vespene)

            for worker in vespene_workers:
                # Get saturated and unsaturated townhalls
                unsaturated_townhalls = self.bot.townhalls.filter(
                    lambda th: th.assigned_harvesters < th.ideal_harvesters)

                if unsaturated_townhalls.exists:
                    unsaturated_townhall = unsaturated_townhalls.closest_to(worker.position)
                    mineral = self.bot.mineral_field.closest_to(unsaturated_townhall)

                    self.bot.do(worker.return_resource(unsaturated_townhall))
                    self.bot.do(worker.gather(mineral, queue=True))

        else:
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
                    mineral = self.bot.mineral_field.closest_to(unsaturated_townhall)

                    self.bot.do(worker.return_resource(unsaturated_townhall))
                    self.bot.do(worker.gather(mineral, queue=True))

            # Move workers from minerals to unsaturated extractors
            if unsaturated_extractors:
                extractor = unsaturated_extractors.first

                mineral_workers = self.bot.workers.filter(
                    lambda worker: worker.is_carrying_minerals)

                if mineral_workers.exists:
                    worker = mineral_workers.closest_to(extractor)

                    self.bot.do(worker.gather(extractor, queue=True))

    async def manage_resources(self):
        """
        Manage idle workers
        """

        await self.manage_minerals()
        await self.manage_vespene()

    async def do_transfuse(self):
        queens = self.bot._units(const.QUEEN)

        for queen in queens:
            if queen.energy >= 50:
                nearby_units = self.bot._units.closer_than(15, queen)
                if nearby_units.exists:
                    nearby_units = nearby_units.sorted(lambda u: u.health_percentage)

                nearby_unit = nearby_units[0]

                # Don't transfuse yourself, fucking asshole.
                if (nearby_unit.tag == queen.tag) and len(nearby_units) > 1:
                    nearby_unit = nearby_units[1]

                if nearby_unit.health_percentage < 0.6 and nearby_unit.type_id != const.ZERGLING:
                    self.bot.do(queen(const.TRANSFUSION_TRANSFUSION, nearby_unit))

    async def keep_main_queens_on_ramp(self):
        ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
        ramp_pos = self.bot.start_location.closest(ramps)
        ramps = [r for r in self.bot._game_info.map_ramps if r.top_center.distance_to(ramp_pos) < 6]

        if ramps:
            # Get main base ramp
            ramp = ramps[0]
        else:
            return

        townhalls = []
        for townhall_tag, queen_tag in self.bot.townhall_queens.items():
            townhall = self.bot._units.find_by_tag(townhall_tag)
            if townhall:
                townhalls.append(townhall)

        if len(townhalls) >= 2:
            townhalls = sorted(townhalls, key=lambda th: th.distance_to(ramp.top_center))
            th1 = townhalls[0]
            th2 = townhalls[1]

            queen1_tag = self.bot.townhall_queens[th1.tag]
            queen2_tag = self.bot.townhall_queens[th2.tag]

            queen1 = self.bot._units.find_by_tag(queen1_tag)
            queen2 = self.bot._units.find_by_tag(queen2_tag)
            if queen1 and queen2:
                ramp_center = (ramp.bottom_center + ramp.top_center) / 2
                for queen, point_offset in zip((queen1, queen2), (Point2((+1, 0)), (Point2((-1, 0))))):
                    if queen.energy < 23 and queen.distance_to(ramp_center) > 3:
                        self.bot.do(queen.attack(ramp_center + point_offset))

    async def manage_queens(self):
        queens = self.bot._units(const.QUEEN)

        # Get townhalls, preferring to assign queens to ready hatcheries
        townhalls = self.bot.townhalls.sorted(lambda th: not th.is_ready)

        await self.do_transfuse()

        # Take this out for now, Not providing much utility
        # await self.keep_main_queens_on_ramp()

        if queens.exists:
            for townhall in townhalls:
                queen_tag = self.bot.townhall_queens.get(townhall.tag)

                if queen_tag is None:
                    # Tag a queen to the townhall
                    untagged_queens = queens.tags_not_in(self.bot.townhall_queens.values())
                    if untagged_queens:
                        queen = untagged_queens[0]
                        self.bot.townhall_queens[townhall.tag] = queen.tag
                    else:
                        # No queens available for this townhall. Continue to next townhall
                        continue
                else:
                    queen = queens.find_by_tag(queen_tag)

                    if queen is None:
                        # Queen died! Untag it
                        del self.bot.townhall_queens[townhall.tag]
                    else:
                        if queen.is_idle:
                            # Move queen to its townhall
                            if queen.distance_to(townhall) > 20:
                                self.bot.do(
                                    queen.attack(townhall.position))

                            if queen.energy >= 25:
                                creep_tumors = self.bot._units({const.CREEPTUMOR, const.CREEPTUMORBURROWED})

                                # Get creep tumors nearby the closest townhall
                                nearby_creep_tumors = creep_tumors.closer_than(17, townhall)

                                # If there are no nearby creep tumors or any at all, then spawn a creep tumor
                                if not nearby_creep_tumors \
                                        and townhall.has_buff(const.QUEENSPAWNLARVATIMER) \
                                        and not self._recent_commands.contains(
                                            ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                            self.bot.state.game_loop):

                                    # Spawn creep tumor if we have none
                                    position = townhall.position.towards_with_random_angle(
                                        self.bot.enemy_start_location, random.randint(5, 7))

                                    self._recent_commands.add(
                                        ResourceManagerCommands.QUEEN_SPAWN_TUMOR,
                                        self.bot.state.game_loop, expiry=50)

                                    self.bot.do(queen(const.BUILD_CREEPTUMOR_QUEEN, position))

                                else:
                                    # Inject larvae
                                    if not townhall.has_buff(const.QUEENSPAWNLARVATIMER):
                                        self.bot.do(queen(const.EFFECT_INJECTLARVA, townhall))

    async def manage_creep_tumors(self):
        creep_tumors = self.bot._units({const.CREEPTUMORBURROWED})

        for tumor in creep_tumors:
            abilities = await self.bot.get_available_abilities(tumor)
            if const.BUILD_CREEPTUMOR_TUMOR in abilities:
                position = tumor.position.towards_with_random_angle(
                    self.bot.enemy_start_location, random.randint(9, 11),
                    max_difference=(math.pi / 2.2))

                # Spawn creep tumors away from expansion locations
                if position.distance_to_closest(self.bot.expansion_locations.keys()) > 5:
                    self.bot.do(tumor(const.BUILD_CREEPTUMOR_TUMOR, position))

    async def read_messages(self):
        for message, val in self.messages.items():

            upgrade_started = {Messages.UPGRADE_STARTED}
            if message in upgrade_started:
                # Ling speed started. Pull workers off vespene
                if val == const.UpgradeId.ZERGLINGMOVEMENTSPEED:
                    self.ack(message)

                    if self.pull_off_gas_early:
                        self._recent_commands.add(
                            ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                            self.bot.state.game_loop, expiry=75)

            new_build = {Messages.NEW_BUILD}
            if message in new_build:
                # Builds to get back onto mining vespene gas
                # We need to be mining vespene for banelings nest
                self.ack(message)
                builds_to_stay_on_vespene = {
                    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
                    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH}
                if val in builds_to_stay_on_vespene:

                    self.pull_off_gas_early = False
                    self._recent_commands.remove(
                        ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE)

            pull_workers_off_vespene = {Messages.PULL_WORKERS_OFF_VESPENE}
            if message in pull_workers_off_vespene:
                # Pull `n` workers off vespene, or set them back to working
                self.ack(message)

                self._ideal_vespene_worker_count = val

            pull_workers_off_vespene_for_x_seconds = {Messages.PULL_WORKERS_OFF_VESPENE_FOR_X_SECONDS}
            if message in pull_workers_off_vespene_for_x_seconds:
                # Pull workers off vespene for `n` seconds
                self.ack(message)
                self._recent_commands.add(
                    ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE,
                    self.bot.state.game_loop, expiry=val)

            return_all_workers_to_vespene = {Messages.CLEAR_PULLING_WORKERS_OFF_VESPENE}
            if message in return_all_workers_to_vespene:
                # Reset all workers back to mining vespene at full saturation
                self.ack(message)

                self._ideal_vespene_worker_count = None
                self._recent_commands.remove(ResourceManagerCommands.PULL_WORKERS_OFF_VESPENE)

            dont_return_distant_workers_to_townhalls = {Messages.DONT_RETURN_DISTANT_WORKERS_TO_TOWNHALLS}
            if message in dont_return_distant_workers_to_townhalls:
                # Turn off returning distant workers to townhalls
                self.ack(message)
                self.allow_return_distant_workers_to_townhalls = False

    async def run(self):
        await super(ResourceManager, self).run()

        await self.read_messages()

        await self.manage_resources()
        await self.manage_queens()
        await self.manage_creep_tumors()
        self.return_distant_workers_to_townhalls()


