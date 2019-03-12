import math
import random
from collections import Counter
from itertools import takewhile
from typing import List, Set, Union

import lib.sc2 as sc2
import lib.sc2.constants as const
from lib.sc2.ids.unit_typeid import UnitTypeId
from lib.sc2.ids.upgrade_id import UpgradeId

import lambdanaut.builds as builds
import lambdanaut.const2 as const2
from lambdanaut.builds import Builds, BuildStages, BUILD_MAPPING, DEFAULT_NEXT_BUILDS
from lambdanaut.const2 import BuildManagerCommands, BuildManagerFlags, DefenseStates, Messages
from lambdanaut.expiringlist import ExpiringList
from lambdanaut.managers import Manager


class BuildManager(Manager):

    name = 'Build Manager'

    def __init__(self, bot, starting_build):
        super(BuildManager, self).__init__(bot)

        assert isinstance(starting_build, Builds)

        self.starting_build: Builds = starting_build

        self.builds: List[Builds] = [
            None,  # Opener
            None,  # Early-game
            None,  # Mid-game
            None,  # Late-game
        ]
        self.build_stage: BuildStages = builds.get_build_stage(starting_build)

        self.build_target: Union[UpgradeId, UnitTypeId] = None
        self.last_build_target: Union[UpgradeId, UnitTypeId] = None

        # Ratio (0.0 - 1.0) of how far we've reached in the current build stage
        self.build_stage_percentage: float = 0.0

        # Flag for if we've already changed the midgame. We only want to do this once
        self.has_switched_midgame = False

        # Flags to decide whether we should disregard worker and townhall build targets
        self.stop_worker_production = False
        self.stop_townhall_production = False

        # If True is in this list, it's equivalent to having stop_worker_production
        # and stop_townhall_production set
        self._stop_nonarmy_production = ExpiringList()

        # Recent commands issued. Uses constants defined in const2.py
        self._recent_commands = ExpiringList()

        # Flags that control the build manager
        self.build_flags: Set[BuildManagerFlags] = set()

        # Message subscriptions
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN)
        self.subscribe(Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_PROXY)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_RUSH)
        self.subscribe(Messages.FOUND_ENEMY_PROXY_HATCHERY)
        self.subscribe(Messages.FOUND_ENEMY_RUSH)
        self.subscribe(Messages.FOUND_ENEMY_WORKER_RUSH)
        self.subscribe(Messages.FOUND_ENEMY_EARLY_GREED)
        self.subscribe(Messages.ENEMY_MOVING_OUT_SCOUTED)
        self.subscribe(Messages.FOUND_ENEMY_EARLY_AGGRESSION)
        self.subscribe(Messages.ENEMY_AIR_TECH_SCOUTED)
        self.subscribe(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)
        self.subscribe(Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD)
        self.subscribe(Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES)
        self.subscribe(Messages.STATE_EXITED)
        self.subscribe(Messages.BUILD_OFFENSIVE_SPINES)
        self.subscribe(Messages.ALLOW_NEURAL_PARASITE_UPGRADE)

        # Expansion index used for trying other expansions if the one we're trying is blocked
        self.next_expansion_index: int = 0

        # Set of the ids of the special build targets that are currently active
        self.active_special_build_target_ids = set()

        # Constant mapping of unit_type to its creation ability for fast access
        # (like the creation ability for spawning a drone)
        self.unit_type_to_creation_ability_map = {
            unit_id: unit.creation_ability for unit_id, unit in self.bot._game_data.units.items()}

        self.build_offensive_spines = False

    async def init(self):
        self.determine_opening_builds()
        self.add_build(self.starting_build)

    @property
    def percentage_done_with_build_stage(self):
        return self.build_stage_index / len()

    def can_afford(self, unit):
        """Returns boolean indicating if the player has enough minerals,
        vespene, and supply to build the unit"""

        can_afford = self.bot.can_afford(unit)
        return \
            can_afford.can_afford_minerals and \
            can_afford.can_afford_vespene and \
            can_afford.have_enough_supply

    def determine_opening_builds(self):
        """
        Sets the self.starting_build and adds other builds based on factors such as:

        * Enemy race
        * Rush distance
        * By-air distance to enemy location
        * Map features
        """

        if len(self.bot.enemy_start_locations) < 3:

            rush_distance = len(self.bot.shortest_path_to_enemy_start_location)

            # Note: Average rush distance is around 153. Longest rush distances are over 160.
            if self.bot.enemy_race is sc2.Race.Terran:
                # Use rush distance to determine build
                # Average rush distance is around 155. Longer rush distances are over 160.
                if rush_distance < 160:
                    # Do ravager harass into macro on small to medium rush distance maps
                    self.starting_build = Builds.OPENER_RAVAGER_HARASS
                elif rush_distance > 165:
                    # Rush distance is long. Play more greedily.
                    self.add_build(Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY)

            elif self.bot.enemy_race is sc2.Race.Protoss:
                # Use rush distance to determine build
                if rush_distance < 150:
                    # Do ravager all ins on short rush distance maps
                    self.starting_build = Builds.RAVAGER_ALL_IN
                elif rush_distance > 155:
                    # Rush distance is long. Play more greedily.
                    self.add_build(Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY)

            elif self.bot.enemy_race is sc2.Race.Zerg:
                if rush_distance < 145:
                    # Play cautiously against zerg on maps with low rush distance
                    # self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)
                    pass

    def check_build_requirements(self, build: Builds) -> bool:
        if build in {Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
                     Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
                     Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE}:
            # Don't switch out of early game spore crawlers
            if Builds.EARLY_GAME_SPORE_CRAWLERS in self.builds:
                return False

        if build in {Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
                     Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
                     Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE}:
            # If we're we have a focused early game build, don't start defending cautiously
            if any(build in self.builds for build in {
                    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
                    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE,
                    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH,
                    Builds.EARLY_GAME_POOL_SPINE_ALL_IN}):
                return False

        if build in {Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH,}:
            # If we're committed to a defense, don't switch to a timing
            if any(build in self.builds for build in {
                    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE,
                    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
                    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS}):

                return False

        return True

    def add_build(self, build: Builds, force=False):
        """
        Adds a build to the build queue
        :param build: The build to be added
        :param force: Skip and build requirements and force the build to be added
        :return:
        """
        assert isinstance(build, Builds)

        build_stage = builds.get_build_stage(build)

        # Check that the build's requirements are met
        if not force and not self.check_build_requirements(build):
            self.print("Skipping build order. It didn't meet requirements: {}".format(build.name))
            return

        self.print("Adding build order: {}".format(build.name))

        # If we're switching the midgame that has already been set, set a flag
        if build_stage == BuildStages.MID_GAME and \
                self.builds[BuildStages.MID_GAME.value] != None:
            self.has_switched_midgame = True

        # Publish a message about the newly added build
        self.publish(Messages.NEW_BUILD, build)

        self.builds[build_stage.value] = build

    def add_next_default_build(self, build: builds.Builds=None):
        """
        Adds the next default build to our builds list(self.builds)
        If `builds` is given, then add the next default build for that build
        Otherwise just add the next default build for our latest build
        """
        if build is None:
            build = self.get_latest_build()
        else:
            build = build

        next_default_build = DEFAULT_NEXT_BUILDS[build]
        if next_default_build is not None:
            self.add_build(next_default_build, force=True)

    def get_latest_build(self) -> builds.Builds:
        """Returns the latest build order added"""
        return list(takewhile(lambda build: build is not None, self.builds))[-1]

    def get_current_build_queue(self):
        """Returns the current build queue"""

        build_queue = []
        for build in self.builds:
            if build is None:
                break
            build_targets = BUILD_MAPPING[build]
            build_queue += build_targets

        return build_queue

    async def read_messages(self):
        """
        Reads incoming subscribed messages and updates the build order based
        on them.
        """

        for message, val in self.messages.items():

            # Messages indicating that it's safe to expand early
            safe_to_expand_early = {Messages.ENEMY_EARLY_NATURAL_EXPAND_TAKEN}
            if message in safe_to_expand_early:
                self.ack(message)

            # Messages indicating to take a cautious early game
            cautious_early_game = {Messages.ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN}
            if message in cautious_early_game:
                self.ack(message)
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS)

            # Messages indicating we need to defend a rush
            rush_detected = {Messages.FOUND_ENEMY_RUSH}
            if message in rush_detected:
                self.ack(message)

                self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)

            worker_rush_detected = {Messages.FOUND_ENEMY_WORKER_RUSH}
            if message in worker_rush_detected:
                self.ack(message)

                # Cancel in-progress structures
                for structure in self.bot.units.filter(
                        lambda u: u.is_structure and u.build_progress < 0.96):
                    self.bot.actions.append(structure(const.AbilityId.CANCEL_BUILDINPROGRESS))

                # Stop any rushing low-worker builds if we scout an enemy worker rush
                self.add_build(Builds.OPENER_DEFAULT)
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)

            # Messages indicating we need to defend an early aggression
            early_aggression = {Messages.FOUND_ENEMY_EARLY_AGGRESSION}
            if message in early_aggression:
                self.ack(message)
                self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)

            # Messages indicating we need to defend a proxy hatchery
            proxy_hatchery_detected = {
                Messages.FOUND_ENEMY_PROXY_HATCHERY}
            if message in proxy_hatchery_detected:
                self.ack(message)

                # Switch to a defensive roach ravager build if we haven't
                # finished a baneling nest yet
                baneling_nests = self.bot.units(const.UnitTypeId.BANELINGNEST)
                if not baneling_nests.ready:

                    # Cancel spawning hatcheries
                    in_prod_hatcheries = self.bot.units(const.UnitTypeId.HATCHERY).not_ready
                    for hatchery in in_prod_hatcheries:
                        self.bot.actions.append(hatchery(const.AbilityId.CANCEL))

                    # Cancel spawning baneling nests
                    for baneling_nest in baneling_nests.not_ready:
                        self.bot.actions.append(baneling_nest(const.AbilityId.CANCEL))

                    self.add_build(Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE)
                    self.add_build(Builds.MID_GAME_ROACH_HYDRA_LURKER)

            # Messages indicating the enemy played greedy early and must be punished :3
            two_base_early_timing = {
                Messages.FOUND_ENEMY_EARLY_GREED}
            if message in two_base_early_timing:
                self.ack(message)

                # Switch to an offensive 2 base build, cancel hatcheries in construction
                if len(self.bot.townhalls) > 2:
                    for townhall in self.bot.townhalls.not_ready:
                        self.bot.actions.append(townhall(const.AbilityId.CANCEL_BUILDINPROGRESS))

                self.add_build(Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH)

            # Switch to Defensive build if early game
            # Stop townhall and worker production for a short duration
            stop_non_army_production = {
                Messages.ENEMY_MOVING_OUT_SCOUTED}
            if message in stop_non_army_production:
                self.ack(message)

                if self.build_stage in {BuildStages.OPENING, BuildStages.EARLY_GAME}:
                    if Builds.EARLY_GAME_SPORE_CRAWLERS not in self.builds:
                        # Switch to a defensive build
                        self.add_build(Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE)
                else:
                    # If we're not in early game, stop building drones/townhalls for a bit
                    self._stop_nonarmy_production.add(
                        True, self.bot.state.game_loop, expiry=25)

            # Messages indicating we need to build spore crawlers
            spore_crawlers_early_game = {Messages.ENEMY_AIR_TECH_SCOUTED}
            if message in spore_crawlers_early_game:
                self.ack(message)
                self.add_build(Builds.EARLY_GAME_SPORE_CRAWLERS)

            # Messages indicating roach_hydra mid game is ideal
            roach_hydra_mid_game = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES,
                Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED,
            }
            if message in roach_hydra_mid_game:
                self.ack(message)
                # Don't change the build if we're rushing to brood lords
                if self.build_stage != BuildStages.LATE_GAME and \
                        Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH not in self.builds:

                    # Cancel spawning baneling nests
                    baneling_nests = self.bot.units(const.UnitTypeId.BANELINGNEST)
                    for baneling_nest in baneling_nests.not_ready:
                        self.bot.actions.append(baneling_nest(const.AbilityId.CANCEL))

                    self.add_build(Builds.MID_GAME_ROACH_HYDRA_LURKER)

            # Messages indicating we need to rush up to brood lords in midgame asap
            broodlord_rush_mid_game = {
                Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD}
            if message in broodlord_rush_mid_game:
                self.ack(message)
            # # # TAKEN OUT FOR NOW BECAUSE THE RUSH SUCKS
            #     if self.build_stage != BuildStages.LATE_GAME:
            #         self.add_build(Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH)

            # Restart townhall and worker production when defending stops
            exit_state = {Messages.STATE_EXITED, }
            if message in exit_state:
                self.ack(message)
                if val == DefenseStates.DEFENDING:
                    self.stop_townhall_production = False
                    self.stop_worker_production = False

            # Stop townhall and worker production during defending
            large_defense = {
                Messages.DEFENDING_AGAINST_MULTIPLE_ENEMIES, }
            if message in large_defense:
                self.ack(message)
                # Only stop non-army production if we have three or more townhalls
                if len(self.bot.townhalls) > 2:
                    self.stop_townhall_production = True
                    self.stop_worker_production = True

            # We should build spine crawlers in opponent's base rather than at home
            build_offensive_spines = {Messages.BUILD_OFFENSIVE_SPINES, }
            if message in build_offensive_spines:
                self.ack(message)
                self.build_offensive_spines = True

            # We should research neural parasite
            research_neural_parasite = {Messages.ALLOW_NEURAL_PARASITE_UPGRADE, }
            if message in research_neural_parasite:
                self.ack(message)
                self.build_flags.add(BuildManagerFlags.ALLOW_NEURAL_PARASITE_UPGRADE)

    def parse_special_build_target(self,
                                   unit: builds.SpecialBuildTarget,
                                   existing_unit_counts: Counter,
                                   build_order_counts: Counter,
                                   build_targets: List) -> Union[const.UnitTypeId, const.UpgradeId, None]:
        """
        Parses a SpecialBuildTarget `unit` and performs relevant mutations on
        `build_order_counts`

        :returns A build target id if it's applicable, else returns None
        """

        assert(isinstance(unit, builds.SpecialBuildTarget))

        if isinstance(unit, builds.AtLeast):
            # AtLeast is a "special" unittype that only adds 1 if we
            # don't have AT LEAST `n` number of units built.

            at_least = unit
            unit = at_least.unit_type
            amount_required = at_least.n

            if build_order_counts[unit] < amount_required:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                else:
                    build_order_counts[unit] = amount_required
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.IfHasThenBuild):
            # IfHasThenBuild is a "special" unittype that only adds `n`
            # unit_type if we have AT LEAST 1 number
            # of if_has_then_build.conditional_unit_type.

            if_has_then_build = unit
            unit = if_has_then_build.unit_type
            conditional_unit_type = if_has_then_build.conditional_unit_type
            amount_to_add = if_has_then_build.n

            if existing_unit_counts[conditional_unit_type] >= 1:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                else:
                    build_order_counts[unit] += amount_to_add
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.IfHasThenDontBuild):
            # IfHasThenDontBuild is a "special" unittype that only adds `n`
            # unit_type if we have 0 of `conditional_unit_type`.

            if_has_then_dont_build = unit
            unit = if_has_then_dont_build.unit_type
            conditional_unit_type = if_has_then_dont_build.conditional_unit_type
            amount_to_add = if_has_then_dont_build.n

            if existing_unit_counts[conditional_unit_type] == 0:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                else:
                    build_order_counts[unit] += amount_to_add
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.OneForEach):
            # OneForEach is a "special" unittype that adds a unittype of
            # `unit_type` to the build queue for each unit_type of `for_each_unit_type`
            # that we already have created.

            one_for_each = unit
            unit = one_for_each.unit_type
            for_each_unit_type = one_for_each.for_each_unit_type

            assert isinstance(for_each_unit_type, const.UnitTypeId)

            existing_for_each_units = len(self.bot.units(for_each_unit_type).ready)

            if existing_for_each_units:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                else:
                    build_order_counts[unit] += existing_for_each_units
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.CanAfford):
            # CanAfford is a "special" unittype that adds a unittype of
            # `unit_type` to the build queue only if we can afford it

            can_afford = unit
            unit = can_afford.unit_type

            if isinstance(unit, builds.SpecialBuildTarget):
                result = self.parse_special_build_target(
                    unit, existing_unit_counts, build_order_counts, build_targets)
                if self.can_afford(result):
                    return result
            elif self.can_afford(unit):
                build_order_counts[unit] += 1
                return unit
            else:
                return unit

        elif isinstance(unit, builds.PullWorkersOffVespeneUntil):
            # PullWorkersOffVespeneUntil is a "special" unittype that pulls `n`
            # workers off vespene until `unit_type` is constructed

            pull_workers_off_vespene_until = unit
            unit = pull_workers_off_vespene_until.unit_type
            amount_of_workers_to_mine = pull_workers_off_vespene_until.n
            special_id = pull_workers_off_vespene_until.id

            if existing_unit_counts[unit]:
                # Return workers to vespene mining
                if special_id in self.active_special_build_target_ids:
                    self.active_special_build_target_ids.discard(special_id)
                    self.publish(Messages.PULL_WORKERS_OFF_VESPENE, None)
                return None
            else:
                # Pull workers off vespene
                if special_id not in self.active_special_build_target_ids:
                    self.active_special_build_target_ids.add(special_id)
                    self.publish(Messages.PULL_WORKERS_OFF_VESPENE, amount_of_workers_to_mine)
                return None

        elif isinstance(unit, builds.PublishMessage):
            # PublishMessage is a "special" unittype that publishes a message
            # the first time this build target is hit.
            # We ensure `build_targets` is empty so that this is called only when
            # it's hit for the first time.

            publish_message = unit
            message = publish_message.message
            value = publish_message.value
            special_id = publish_message.id

            if special_id not in self.active_special_build_target_ids \
                    and not build_targets:
                self.active_special_build_target_ids.add(special_id)
                self.publish(message, value)

            return None

        elif isinstance(unit, builds.IfFlagIsSet):
            # IfFlagIsSet is a "special" unittype that only adds `n`
            # unit_type if the BuildMangerFlags `flag` is set

            if_flag_is_set = unit
            unit = if_flag_is_set.unit_type
            flag = if_flag_is_set.flag
            amount_to_add = if_flag_is_set.n

            if flag in self.build_flags:
                if isinstance(unit, builds.SpecialBuildTarget):
                    return self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                else:
                    build_order_counts[unit] += amount_to_add
                    return unit
            else:
                return unit

        elif isinstance(unit, builds.RunFunction):
            # RunFunction is a "special" unittype that runs a function the
            # first time this build target is hit.
            # We ensure `build_targets` is empty so that this is called only when
            # it's hit for the first time.

            run_function = unit
            func = run_function.function
            special_id = run_function.id

            if special_id not in self.active_special_build_target_ids \
                    and not build_targets:
                self.active_special_build_target_ids.add(special_id)

                # Record the result in run_function
                run_function.result = func(self.bot)

            return None

    def overlord_is_build_target(self) -> bool:
        """
        Build Overlords automatically once the bot has built three or more
        Overlords
        """

        # Only build overlords if we haven't yet reached max supply
        if self.bot.supply_cap < 200:
            # Subtract supply from damaged overlords. Assume we'll lose them.
            overlords = self.bot.units(
                {const.OVERLORD, const.UnitTypeId.OVERLORDTRANSPORT, const.UnitTypeId.OVERSEER})
            damaged_overlord_supply = 0
            if overlords:
                damaged_overlords = overlords.filter(lambda o: o.health_percentage < 0.85)
                if damaged_overlords.exists:
                    damaged_overlord_supply = len(damaged_overlords) * 8  # Overlords provide 8 supply

            # Calculate the supply coming from overlords in eggs
            overlord_egg_count = self.bot.already_pending(const.OVERLORD)
            overlord_egg_supply = overlord_egg_count * 8  # Overlords provide 8 supply

            # Calculate the supply coming from nearly-done hatcheries
            hatcheries_in_progress_count = len(self.bot.units(const.HATCHERY).filter(
                lambda u: not u.is_ready and u.build_progress > 0.65))
            hatcheries_in_progress_supply = hatcheries_in_progress_count * 6  # Hatcheries provide 6 supply

            supply_left = \
                self.bot.supply_left \
                + overlord_egg_supply \
                + hatcheries_in_progress_supply\
                - damaged_overlord_supply

            # Controls how soon we build overlords when we near supply cap.
            # The lower this is, the earlier we'll build overlords. = Conservative
            # The higher this is, the later we'll build overlords. = More prone to supply block
            supply_cap_factor = 10

            if supply_left < 2 + self.bot.supply_cap / supply_cap_factor:
                # With a formula like this, At 20 supply cap it'll build an overlord
                # when you have 7 supply left. At 40 supply cap it'll build an overlord
                # when you have 11 supply left. This seems reasonable and conservative.
                # It seems

                # Ensure we have over 3 overlords.
                if len(overlords) >= 3:
                    return True

        return False

    def current_build_targets(self, n_targets=6) -> List[const.UnitTypeId]:
        """
        Goes through the build order one by one counting up all the units and
        stopping once we hit a unit we don't yet have.

        `n_targets` specifies the number of build targets to return.
        """

        build_targets = []

        if self.overlord_is_build_target():
            unit = const.OVERLORD
            self.last_build_target = self.build_target
            self.build_target = unit
            return [unit]

        # Count of existing units {unit.type_id: count}
        existing_unit_counts = Counter(map(lambda unit: unit.type_id, self.bot.units))

        # Count of units being trained or built
        pending_units = Counter({u: self.bot.already_pending(u, all_units=True) for u in const2.ZERG_UNITS})

        # Add an extra zergling for each zergling in an egg
        zergling_creation_ability = self.bot._game_data.units[const.ZERGLING.value].creation_ability
        zergling_eggs = Counter({
            const.ZERGLING: sum(
                [egg.orders[0].ability == zergling_creation_ability
                 for egg in self.bot.units(const.UnitTypeId.EGG)]
            )
        })

        # Burrowed Zerglings count as zerglings
        burrowed_zergling = Counter({const.ZERGLING: len(self.bot.units(const.ZERGLINGBURROWED))})

        # Burrowed Banelings count as banelings
        burrowed_banelings = Counter({const.BANELING: len(self.bot.units(const.BANELINGBURROWED))})

        # Burrowed Roaches count as roaches
        burrowed_roaches = Counter({const.ROACH: len(self.bot.units(const.ROACHBURROWED))})

        # Burrowed Lurkers count as lurkers
        burrowed_lurkers = Counter({const.LURKERMP: len(self.bot.units(const.LURKERMPBURROWED))})

        # Burrowed Infestors count as infestors
        burrowed_infestors = Counter({const.INFESTOR: len(self.bot.units(const.INFESTORBURROWED))})

        # Hives count as Lairs. This is a weird one that doesn't make a lot of sense
        # Reasoning is that when we get a Hive, we don't want the AI to act like we don't have a Lair
        hives_as_lairs = Counter({const.LAIR: len(self.bot.units(const.HIVE))})

        # Uprooted spine crawlers count as spine crawlers
        spine_crawlers_uprooted = Counter({const.SPINECRAWLER: len(
            self.bot.units(const.UnitTypeId.SPINECRAWLERUPROOTED))})

        # Uprooted spore crawlers count as spine crawlers
        spore_crawlers_uprooted = Counter({const.SPORECRAWLER: len(
            self.bot.units(const.UnitTypeId.SPORECRAWLERUPROOTED))})

        # Extractors without vespene left
        empty_extractors = Counter({const.EXTRACTOR: len(
            self.bot.units(const.EXTRACTOR).filter(lambda extr: extr.vespene_contents == 0))
        })

        # Count of pending upgrades
        existing_and_pending_upgrades = Counter({u: math.ceil(self.bot.already_pending_upgrade(u))
                                                 for u in const2.ZERG_UPGRADES})

        existing_unit_counts += pending_units
        existing_unit_counts += zergling_eggs
        existing_unit_counts += burrowed_zergling
        existing_unit_counts += burrowed_banelings
        existing_unit_counts += burrowed_roaches
        existing_unit_counts += burrowed_lurkers
        existing_unit_counts += burrowed_infestors
        existing_unit_counts += hives_as_lairs
        existing_unit_counts += spine_crawlers_uprooted
        existing_unit_counts += spore_crawlers_uprooted
        existing_unit_counts -= empty_extractors  # Subtract empty extractors
        existing_unit_counts += existing_and_pending_upgrades

        # Set the number of hatcheries to be the number of town halls with minerals left
        # (We want to count Lairs and Hives as hatcheries too. They're all expansions)
        townhalls = self.bot.townhalls
        if townhalls:
            townhall_count = 0
            for townhall in townhalls:
                minerals = self.bot.state.mineral_field
                if minerals.exists:
                    nearby_minerals = minerals.closer_than(10, townhall)
                    if nearby_minerals.exists:
                        townhall_count += 1

            existing_unit_counts[const.HATCHERY] = townhall_count

        # Count of units in build order up till this point {unit.type_id: count}
        build_order_counts = Counter()

        # Go through each build looking for the unit we don't have
        last_build = None
        for build in self.builds:
            if build is None:
                # Reached end of build
                return []

            if last_build in builds.FORCE_DEFAULT_NEXT_BUILDS:
                # The last build was in our `FORCE_DEFAULT_NEXT_BUILDS` set.
                # Return empty so that we set its default next build
                self.add_next_default_build(last_build)
                return []

            build_queue = builds.BUILD_MAPPING[build]

            for unit_i in range(len(build_queue)):
                unit = build_queue[unit_i]

                # Count each unit in the queue as we loop through them
                # Check if the unit is a special conditional unittype
                if isinstance(unit, builds.SpecialBuildTarget):
                    result = self.parse_special_build_target(
                        unit, existing_unit_counts, build_order_counts, build_targets)
                    if result is not None:
                        unit = result
                else:
                    build_order_counts[unit] += 1

                # Check if we have enough of this unit built already
                if existing_unit_counts[unit] < build_order_counts[unit]:

                    # Check if we have the tech requirement for this unit built already
                    tech_requirement = None
                    idle_building_structure = None
                    if isinstance(unit, const.UnitTypeId):
                        # Check for unit tech requirements
                        tech_requirement = self.bot._game_data.units[unit.value].tech_requirement
                        idle_building_structure = None
                    elif isinstance(unit, const.UpgradeId):
                        # Check for upgrade tech requirements
                        tech_requirement = const2.ZERG_UPGRADES_TO_TECH_REQUIREMENT[unit]
                        idle_building_structure = self.bot.units(const2.ZERG_UPGRADES_TO_STRUCTURE[unit]).ready.idle

                    # Skip worker and townhall build targets if these flags are set
                    if (self.stop_townhall_production or
                        self._stop_nonarmy_production.contains(True, self.bot.state.game_loop)) and \
                            unit in const2.UNUPGRADED_TOWNHALLS:
                        first_tier_production_structures = {const.SPAWNINGPOOL, const.GATEWAY, const.BARRACKS}
                        if self.bot.units(first_tier_production_structures):
                            continue
                    elif (self.stop_worker_production or
                          self._stop_nonarmy_production.contains(True, self.bot.state.game_loop)) and \
                            unit in const2.WORKERS:
                        first_tier_production_structures = {const.SPAWNINGPOOL, const.GATEWAY, const.BARRACKS}
                        if self.bot.units(first_tier_production_structures):
                            continue

                    # Skip banelings if we don't have any idle zerglings
                    if unit is const.BANELING and not self.bot.units(const.ZERGLING).idle:
                        continue

                    if (tech_requirement is None or existing_unit_counts[tech_requirement]) > 0 and \
                            (idle_building_structure is None or idle_building_structure.exists):

                        # Found build target
                        self.last_build_target = self.build_target
                        self.build_target = unit

                        # Update build_stage_index if we haven't started accumulating build_targets
                        if not build_targets:
                            self.build_stage_percentage = unit_i / len(build_queue)

                        build_stage = builds.get_build_stage(build)
                        if build_stage != self.build_stage and build_targets == []:
                            # Update build stage
                            self.build_stage = build_stage

                            # Return workers to vespene that we took off from previous build stages
                            self.publish(Messages.PULL_WORKERS_OFF_VESPENE)

                            # Publish the new build stage
                            self.publish(Messages.NEW_BUILD_STAGE, build_stage)

                        # Return early if the next build target is a town hall.
                        # This prevents sending worker to create townhall before
                        # its time
                        if unit in const2.TOWNHALLS:
                            if not build_targets:
                                return [unit]
                            else:
                                return build_targets

                        # Return early if the next build target is built from a structure
                        # This prevents queuing up multiple units at a single structure.
                        if unit in const2.ZERG_UNITS_FROM_STRUCTURES:
                            if not build_targets:
                                return [unit]
                            else:
                                return build_targets

                        # Return early if the next build target is an upgrade
                        # This prevents queuing up multiple upgrades at a single structure.
                        if isinstance(unit, const.UpgradeId):
                            if not build_targets:
                                return [unit]
                            else:
                                return build_targets

                        # Add the build target
                        build_targets.append(unit)

                        # Pretend like we have this unit already and see if
                        # there are more units we can add to the build_targets list
                        existing_unit_counts[unit] += 1

                        # If we have enough build targets, return.
                        if len(build_targets) == n_targets:
                            return build_targets

            last_build = build

        return build_targets

    async def create_build_target(self, build_target) -> bool:
        """
        Main function that issues commands to build a build order target

        Returns a boolean indicating if the build was a success
        """

        if self.last_build_target != build_target:
            self.print("Build target: {}".format(build_target))

        # Check type of unit we're building to determine how to build

        if build_target is const.HATCHERY:
            expansion_locations = await self.bot.get_open_expansions()
            try:
                expansion_location = expansion_locations[self.next_expansion_index]
            except IndexError:
                self.print("Couldn't build expansion. All spots are taken.")
                self.next_expansion_index = 0
                return False

            # Get drones that aren't carrying minerals or gas
            drones = self.bot.units(const.DRONE).filter(
                lambda d: not d.is_carrying_minerals and not d.is_carrying_vespene)

            if self.can_afford(build_target):
                if drones:
                    drone = drones.closest_to(expansion_location)

                    err = await self.bot.do(drone.build(build_target, expansion_location))

                    if err:
                        # Try the next expansion location
                        self.print("Error while building the expansion at {}. "
                                   "Trying the next expansion location. ".format(expansion_location))
                        self.next_expansion_index += 1
                    else:
                        # Expansion worked! Reset expansion index.
                        self.next_expansion_index = 0
                        return True

            # Move drone to expansion location before construction
            elif self.bot.state.common.minerals > 200 and \
                    not self._recent_commands.contains(
                        BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop):
                if expansion_location:
                    if drones:
                        nearest_drone = drones.closest_to(expansion_location)
                        # Only move the drone to the expansion location if it's far away
                        # To keep from constantly issuing move commands
                        if nearest_drone.distance_to(expansion_location) > 9:
                            self.bot.actions.append(nearest_drone.move(expansion_location))

                            self.publish(Messages.DRONE_LEAVING_TO_CREATE_HATCHERY, nearest_drone.tag)

                            # Keep from issuing another expand move command
                            self._recent_commands.add(
                                BuildManagerCommands.EXPAND_MOVE, self.bot.state.game_loop, expiry=22)

        elif build_target is const.LAIR:
            # Get a hatchery
            hatcheries = self.bot.units(const.HATCHERY).idle

            # Train the unit
            if self.can_afford(build_target) and hatcheries:
                hatchery = hatcheries.closest_to(self.bot.start_location)
                self.bot.actions.append(hatchery.build(build_target))
                return True

        elif build_target is const.HIVE:
            # Get a lair
            lairs = self.bot.units(const.LAIR).idle

            # Train the unit
            if self.can_afford(build_target) and lairs:
                self.bot.actions.append(lairs.random.build(build_target))
                return True

        elif build_target is const.EXTRACTOR:
            if self.can_afford(build_target):
                townhalls = self.bot.townhalls.ready
                for townhall in townhalls:
                    extractors = self.bot.units(const2.VESPENE_REFINERIES)
                    geysers = self.bot.state.vespene_geyser.filter(lambda g: extractors.closer_than(0.5, g).empty)
                    geyser = geysers.closest_to(townhall)

                    if geyser.distance_to(townhall) > 9:
                        continue

                    drone = self.bot.workers.closest_to(geyser)

                    self.bot.actions.append(drone.build(build_target, geyser))

                    return True

        elif build_target is const.GREATERSPIRE:
            # Get a spire
            spire = self.bot.units(const.SPIRE).idle

            # Train the unit
            if spire.exists and self.can_afford(build_target):
                self.bot.actions.append(spire.random.build(build_target))

                return True

        elif build_target is const.SPINECRAWLER:
            if self.build_offensive_spines:
                if self.can_afford(build_target):
                    # Build offensive spine crawlers
                    target = self.bot.enemy_start_location.towards_with_random_angle(
                        self.bot.start_location, 2)

                    await self.bot.build(build_target, near=target)

            else:
                # Build defensive spine crawlers
                townhalls = self.bot.townhalls.ready

                if townhalls.exists:
                    if self.can_afford(build_target):
                        enemy_start_location = self.bot.enemy_start_location
                        townhall = townhalls.random
                        nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                        nearby_ramp = townhall.position.towards(
                            enemy_start_location, 1).closest(nearby_ramps)

                        if nearby_ramp.distance_to(townhall) < 18:
                            target = nearby_ramp
                        else:
                            near_townhall = townhall.position.towards_with_random_angle(
                                enemy_start_location, 10, max_difference=(math.pi / 2.0))
                            target = near_townhall

                        position = await self.bot.find_placement(
                            const.SPINECRAWLER, target, max_distance=25)

                        await self.bot.build(build_target, near=position)

                        return True

        elif build_target is const.SPORECRAWLER:
            townhalls = self.bot.townhalls.ready

            if townhalls:
                if self.can_afford(build_target):
                    spore_crawlers = self.bot.units(const.SPORECRAWLER)

                    target = None
                    if spore_crawlers:
                        # Attempt to find a townhall with no sporecrawlers
                        for townhall in townhalls:
                            near_sc = spore_crawlers.closer_than(6, townhall)
                            if not len(near_sc):
                                target = self.bot.point_between_townhall_and_resources(townhall)
                                towards_resources = townhall.position.towards_with_random_angle(target, 2)
                                target = towards_resources

                                break
                        else:
                            # If all townhalls are saturated with spore crawlers, find a nearby ramp
                            nearby_ramps = [ramp.top_center for ramp in self.bot._game_info.map_ramps]
                            nearby_ramps = [ramp for ramp in nearby_ramps
                                            if townhalls.closer_than(20, ramp)]
                            if nearby_ramps:
                                # Sort ramps closest to start location
                                nearby_ramps = sorted(
                                    nearby_ramps,
                                    key=lambda r: r.distance_to(self.bot.start_location))

                                for ramp in nearby_ramps:
                                    if not spore_crawlers.closer_than(6, ramp):
                                        target = ramp

                    if target is None:
                        townhall = townhalls.random.position
                        target = self.bot.point_between_townhall_and_resources(townhall)
                        towards_resources = townhall.position.towards_with_random_angle(target, 2)
                        target = towards_resources

                    await self.bot.build(build_target, near=target)

                    return True

        elif build_target in const2.ZERG_STRUCTURES_FROM_DRONES:
            townhalls = self.bot.townhalls.ready

            if townhalls.exists:
                if self.can_afford(build_target):
                    townhall = townhalls.closest_to(self.bot.start_location)
                    location = townhall.position

                    # Attempt to build the structure away from the nearest minerals
                    nearest_minerals = self.bot.state.mineral_field.closer_than(8, townhall)
                    nearest_gas = self.bot.state.vespene_geyser.closer_than(8, townhall)
                    nearest_resources = nearest_minerals | nearest_gas
                    if nearest_resources.exists:

                        away_from_resources = townhall.position.towards_with_random_angle(
                            nearest_resources.center, random.randint(-13, -2),
                            max_difference=(math.pi / 2.8),
                        )
                        location = away_from_resources

                    await self.bot.build(build_target, near=location)

                    return True

        elif build_target is const.QUEEN:

            townhalls = self.bot.townhalls.ready.idle

            # Prefer using a townhall that doesn't already have a queen.
            preferred_townhalls = townhalls.filter(
                lambda th: th.tag not in self.bot.townhall_queens)

            if preferred_townhalls:
                townhalls = preferred_townhalls

            if self.can_afford(build_target) and townhalls:
                self.bot.actions.append(
                    townhalls.random.train(build_target))

                return True

        elif build_target in const2.ZERG_UNITS_FROM_LARVAE:
            # Get larva
            larvas = self.bot.units(const.LARVA)

            # Train the unit
            if self.can_afford(build_target) and larvas:

                unsaturated_townhalls = self.bot.townhalls.sorted(
                    lambda th: th.assigned_harvesters / th.ideal_harvesters if th.ideal_harvesters else 1)

                if unsaturated_townhalls:
                    if build_target is const.DRONE:
                        # Prefer building drones from unsaturated townhalls
                        townhall = unsaturated_townhalls[0]
                        larva = larvas.closest_to(townhall)
                    else:
                        # Prefer building other units from saturated townhalls
                        townhall = unsaturated_townhalls[0]
                        larva = larvas.furthest_to(townhall)
                else:
                    larva = larvas.random


                if build_target == const.OVERLORD:
                    # Keep from issuing another overlord build command too soon
                    # Overlords are built in 18 seconds.
                    self._recent_commands.add(
                        BuildManagerCommands.BUILD_OVERLORD, self.bot.state.game_loop, expiry=18)

                self.bot.actions.append(larva.train(build_target))
                return True

        elif build_target is const.BANELING:
            # Get zerglings
            zerglings = self.bot.units(const.ZERGLING).idle

            # Train the unit
            if self.can_afford(build_target) and zerglings:
                zergling = zerglings.closest_to(self.bot.start_location)
                self.bot.actions.append(zergling.stop())
                self.bot.actions.append(zergling.train(build_target, queue=True))
                return True

        elif build_target is const.RAVAGER:
            # Get roaches
            roaches = self.bot.units(const.ROACH).filter(
                lambda r: not self.bot.unit_is_engaged(r))

            # Train the unit
            if self.can_afford(build_target) and roaches:
                roach = roaches.closest_to(self.bot.start_location)
                self.bot.actions.append(roach.stop())
                self.bot.actions.append(roach.train(build_target, queue=True))
                return True

            # Return True regardless.
            # We can skip the ravager if all the roaches are engaged
            return True

        elif build_target is const.LURKERMP:
            # Get hydras
            hydralisks = self.bot.units(const.HYDRALISK).filter(
                lambda r: not self.bot.unit_is_engaged(r))

            # Train the unit
            if self.can_afford(build_target) and hydralisks:
                hydralisk = hydralisks.closest_to(self.bot.start_location)
                self.bot.actions.append(hydralisk.stop())
                self.bot.actions.append(hydralisk.train(build_target, queue=True))
                return True

            # Return True regardless.
            # We can skip the lurker if all the hydralisks are engaged
            return True

        elif build_target is const.BROODLORD:
            # Get a Corruptor
            corruptors = self.bot.units(const.CORRUPTOR)

            # Train the unit
            if self.can_afford(build_target) and corruptors:
                # Prefer idle corruptors if they exist
                idle_corruptors = corruptors.idle
                if idle_corruptors.exists:
                    corruptors = idle_corruptors

                corruptor = corruptors.closest_to(self.bot.start_location)
                self.bot.actions.append(corruptor.train(build_target))
                return True

        elif build_target is const.OVERSEER:
            # Get an overlord
            overlords = self.bot.units(const.OVERLORD)

            # Train the unit
            if self.can_afford(build_target) and overlords.exists:
                overlord = overlords.closest_to(self.bot.start_location)
                self.bot.actions.append(overlord.train(build_target))
                return True

        # Upgrades below
        elif isinstance(build_target, const.UpgradeId):
            upgrade_structure_type = const2.ZERG_UPGRADES_TO_STRUCTURE[build_target]
            upgrade_structures = self.bot.units(upgrade_structure_type).ready
            if self.can_afford(build_target) and upgrade_structures:

                # Require idle upgrade structures
                if upgrade_structures.idle.exists:
                    upgrade_structures = upgrade_structures.idle

                upgrade_ability = self.bot._game_data.upgrades[build_target.value].research_ability.id
                self.bot.actions.append(upgrade_structures.first(upgrade_ability))

                # Send out message about upgrade started
                self.publish(Messages.UPGRADE_STARTED, build_target)

                return True

        else:
            self.print("Could not determine how to create build_target `{}`".format(build_target))

        return False

    async def create_build_targets(self, build_targets: list) -> bool:
        """
        Creates a list of build targets, stopping at the first one that is
        unable to be built. Returns a boolean indicating if they were all
        built
        """

        for build_target in build_targets:
            result = await self.create_build_target(build_target)
            if not result:
                return False

        return True

    async def run(self):
        # Read messages and act on them
        await self.read_messages()

        if self.bot.minerals > 24:
            # Get the current build target
            current_build_targets = self.current_build_targets()

            if not current_build_targets:
                # If we are at the end of the build queue, then add a default build
                self.add_next_default_build()
            else:
                # Build the current build targets
                await self.create_build_targets(current_build_targets)
