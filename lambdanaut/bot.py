from collections import defaultdict
import copy
import itertools
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

import lib.sc2 as sc2
import lib.sc2.constants as const
from lib.sc2.position import Point2, Point3
from lib.sc2.pixel_map import PixelMap
from lib.sc2.unit import Unit
from lib.sc2.units import Units
import numpy

from lambdanaut import VERSION, DEBUG, CREATE_DEBUG_UNITS
import lambdanaut.builds as builds
import lambdanaut.const2 as const2
import lambdanaut.clustering as clustering
from lambdanaut.managers import Manager
from lambdanaut.managers.build import BuildManager
from lambdanaut.managers.defense import DefenseManager
from lambdanaut.managers.force import ForceManager
from lambdanaut.managers.intel import IntelManager
from lambdanaut.managers.micro import MicroManager
from lambdanaut.managers.overlord import OverlordManager
from lambdanaut.managers.resource import ResourceManager
from lambdanaut.pathfinding import Pathfinder
import lambdanaut.unit_cache as unit_cache
import lambdanaut.utils as utils

from lambdanaut.const2 import Messages
from lambdanaut.builds import Builds


BUILD = Builds.OPENER_DEFAULT


class Lambdanaut(sc2.BotAI):
    def __init__(self, **kwargs):
        """
        :param kwargs: Optional flags to alter bot behavior
        """
        super(Lambdanaut, self).__init__()

        self.debug = DEBUG

        self.kwargs = kwargs

        self.intel_manager: IntelManager = None
        self.build_manager: BuildManager = None
        self.resource_manager: ResourceManager = None
        self.overlord_manager: OverlordManager = None
        self.force_manager: ForceManager = None
        self.defense_manager: DefenseManager = None
        self.micro_manager: MicroManager = None

        self.managers = set()

        self.iteration = 0

        # "Do" actions to run
        self.actions = []

        # Message subscriptions
        self._message_subscriptions: Dict[const2.Messages, List[Manager]] = defaultdict(list)

        # Global Intel
        self.enemy_start_location: Point2 = None
        self.not_enemy_start_locations: Set[Point2] = None

        # Set of tags of units currently occupied in some way. Don't order them.
        # This is cleared every time an attack ends
        self.occupied_units: Set[int] = set()

        # Townhall tag -> Queen tag mapping of what queens belong to what townhalls
        self.townhall_queens: Dict[int, int] = {}

        # Set of worker ids of workers currently defending an attack.
        self.workers_defending: Set[int] = set()

        # Map of all our unit's tags to UnitCached objects with their remembered
        # properties (Last health, shields, location, etc)
        self.unit_cache = {}

        # Map of all our unit's tags to UnitCached objects with their remembered
        # properties (Last health, shields, location, etc)
        self.enemy_cache = {}

        # Clusters to be set on the first iteration
        self.army_clusters: List[clustering.Cluster] = None
        self.enemy_clusters: List[clustering.Cluster] = None

        # Fastest path to the enemy start location
        self.shortest_path_to_enemy_start_location: List[Tuple[int, int]] = None

        # Blank pixel map for use in algorithms
        self.blank_pixel_map: PixelMap = None

        # Copy of self.game_info.pathing_grid except the starting structures are removed
        self.pathing_grid: PixelMap = None

        # Sets enemy_race.
        # This is a hack to fix a bug on our test maps.
        try:
            self.enemy_race = super(Lambdanaut, self).enemy_race
        except AttributeError:
            self.enemy_race = sc2.data.Race.Zerg

    async def on_step(self, iteration):
        self.iteration = iteration

        if iteration == 0:
            # Our army clusters
            self.army_clusters = clustering.get_fresh_clusters(
                [], k=8, center_around=self.game_info.map_center)

            # Our enemy clusters
            self.enemy_clusters = clustering.get_fresh_clusters(
                [], k=7, center_around=self.game_info.map_center)

            # Update the default builds based on the enemy's race
            builds.update_default_builds(self.enemy_race)

            # Setup Global Intel variables
            try:
                self.enemy_start_location = self.enemy_start_locations[0]
            except IndexError:
                self.enemy_start_location = self.game_info.map_center
            self.not_enemy_start_locations = {self.start_location}

            # Update our local copies of different pixel maps (pathing_grid, blank_pixel_map, etc...)
            self.update_pixel_maps()

            # Update the pathing variables
            self.update_shortest_path_to_enemy_start_location()

            # Load up managers
            self.intel_manager = IntelManager(self)
            self.build_manager = BuildManager(
                self, starting_build=BUILD)
            self.resource_manager = ResourceManager(self)
            self.overlord_manager = OverlordManager(self)
            self.force_manager = ForceManager(self)
            self.defense_manager = DefenseManager(self)
            self.micro_manager = MicroManager(self)

            self.managers = {
                self.intel_manager,
                self.build_manager,
                self.resource_manager,
                self.overlord_manager,
                self.force_manager,
                self.defense_manager,
                self.micro_manager,
            }

            # Initialize managers
            for manager in self.managers:
                await manager.init()

            # Load bot kwargs(passed into Lambdanaut.__init__)
            for key, value in self.kwargs.items():
                if key is 'starting_build':
                    # Alter starting build
                    self.build_manager.starting_build = value

                elif key is 'additional_builds':
                    assert isinstance(value, list)
                    for build in value:
                        self.build_manager.add_build(build, force=True)

            await self.chat_send("λ LΛMBDANAUT λ - {}".format(VERSION))

        # Update the unit cache with remembered friendly and enemy units
        self.update_unit_caches()

        await self.intel_manager.run()  # Run before all other managers

        await self.resource_manager.run()
        await self.build_manager.run()
        await self.force_manager.run()
        await self.defense_manager.run()
        await self.micro_manager.run()

        # Do this more rarely. Less important. Start on second iteration.
        if iteration % 5 == 2:
            await self.overlord_manager.run()

        # Update the unit clusters
        if iteration % 5 == 0:
            self.update_clusters()

        if self.debug:
            await self.draw_debug()
            if CREATE_DEBUG_UNITS:
                await self.create_debug_units()

        # "Do" actions
        await self.do_actions(self.actions)

        # Reset actions
        self.actions = []

    async def on_unit_created(self, unit):
        self.publish(None, Messages.UNIT_CREATED, unit)

        # Always allow banelings to attack structures
        # Commented out
        # if unit.type_id == const.BANELING:
        #     self.actions.append(unit(const.BEHAVIOR_BUILDINGATTACKON))

    async def on_unit_destroyed(self, unit_tag):
        # Remove destroyed units from caches
        if unit_tag in self.unit_cache:
            del self.unit_cache[unit_tag]
        if unit_tag in self.enemy_cache:
            del self.enemy_cache[unit_tag]

    async def on_building_construction_complete(self, unit: Unit):
        self.publish(None, Messages.STRUCTURE_COMPLETE, unit)

    @property
    def start_location(self) -> Point2:
        """Set start location to map center if there is not one"""
        return self.game_info.player_start_location or self.game_info.map_center

    @property
    def pathable_start_location(self):
        """Pathable point near start location"""
        return self.find_nearby_pathable_point(self.start_location)

    @property
    def start_location_to_enemy_start_location_distance(self):
        return self.start_location.distance_to(self.enemy_start_location)

    async def create_debug_units(self):
        # Create units on condition
        # zerglings = self.units(const.ZERGLING)
        # if len(zerglings) > 10:
        #     await self._client.debug_create_unit([[const.ZERGLING, 15, zerglings.random.position, 2]])
        #
        # if self.iteration == 25:
        #       drones = self.units(const2.WORKERS)
        #       await self._client.debug_create_unit([[const.ZERGLING, 11, drones.random.position, 1]])
        #       await self._client.debug_create_unit([[const.ZERGLING, 15, drones.random.position, 2]])

        # Create Units every 15 iterations
        if self.iteration % 15 == 0:

            hatch = self.units(const.HATCHERY)
            # await self._client.debug_create_unit([[const.INFESTOR, 1, self.start_location - Point2((4, 0)), 1]])
            # await self._client.debug_create_unit([[const.BANELING, 2, hatch.random.position + Point2((6, 0)), 2]])
            # await self._client.debug_create_unit([[const.ZERGLING, 7, hatch.random.position + Point2((6, 0)), 2]])
            # await self._client.debug_create_unit([[const.ROACH, 1, hatch.random.position + Point2((11, 0)), 1]])
            # await self._client.debug_create_unit([[const.ROACH, 2, hatch.random.position + Point2((6, 0)), 2]])

        # Create banelings and zerglings every 15 steps
        # For testing micro maps
        #
        import random
        friendly = self.units
        enemy = self.known_enemy_units
        if not friendly or not enemy:
            print("FRIENDLY COUNT: {}".format(len(friendly)))
            print("ENEMY COUNT: {}".format(len(enemy)))
            if friendly | enemy:
                await self._client.debug_kill_unit(friendly | enemy)

            self.force_manager.dont_stop_attacking = True; self.force_manager.state = const2.ForcesStates.ATTACKING

            # await self._client.debug_create_unit([[const.ZERGLING, 22, self.start_location - Point2((10, 0)), 1]])
            await self._client.debug_create_unit([[const.ZERGLING, 15, self.start_location - Point2((10, 0)), 1]])
            await self._client.debug_create_unit([[const.BANELING, 4, self.start_location - Point2((12, 0)), 1]])
            await self._client.debug_create_unit([[const.UnitTypeId.ZERGLING, 40, self.start_location + Point2((5, 0)), 2]])
            # await self._client.debug_create_unit([[const.PHOTONCANNON, 6, self.start_location + Point2((6, 0)), 2]])
            await self._client.debug_create_unit([[const.PYLON, 1, self.start_location + Point2((8, 0)), 2]])
            # await self._client.debug_create_unit([[const.SUPPLYDEPOT, 3, self.start_location + Point2((6, 0)), 2]])
            # await self._client.debug_create_unit([[const.PROBE, 20, self.start_location + Point2((9, 0)), 2]])
            # await self._client.debug_create_unit([[const.NEXUS, 1, self.start_location + Point2((2, 0)), 2]])
            # await self._client.debug_create_unit([[const.MARINE, 12, self.start_location + Point2((6, 0)), 2]])
        # await self._client.debug_create_unit([[const.MARINE, 17, self.start_location + Point2((7, 0)), 2]])
        #     await self._client.debug_create_unit([[const.ZERGLING, 3, self.start_location + Point2((7, random.randint(-7, +7))), 2]])
        #     await self._client.debug_create_unit([[const.ZERGLING, 10, self.start_location + Point2((7, random.randint(-7, +7))), 2]])
        #     await self._client.debug_create_unit([[const.ZERGLING, 20, self.start_location + Point2((7, random.randint(-7, +7))), 2]])
        # await self._client.debug_create_unit([[const.DRONE, 30, self.start_location + Point2((5, 0)), 1]])
        # await self._client.debug_create_unit([[const.ZERGLING, 20, self.start_location + Point2((4, 0)), 1]])
        # await self._client.debug_create_unit([[const.BANELING, 2, hatch.random.position + Point2((6, 0)), 2]])
        # await self._client.debug_create_unit([[const.HATCHERY, 1, self.start_location - Point2((11, 0)), 1]])
        # await self._client.debug_create_unit([[const.ZERGLING, 5, self.start_location + Point2((7, 0)), 2]])
        # await self._client.debug_create_unit([[const.SPINECRAWLER, 6, self.start_location + Point2((8, 0)), 2]])

    async def draw_debug(self):
        """
        Draws debug images on screen during game
        """

        class Green:
            r = 0
            g = 255
            b = 0

        class Red:
            r = 255
            g = 0
            b = 0

        # Draw clusters
        for cluster in self.army_clusters:
            if cluster:
                radius = cluster.position.distance_to_furthest(cluster)
                cluster_position = cluster.position.to3
                cluster_position += Point3((0, 0, 6))
                self._client.debug_sphere_out(cluster_position, radius, color=Green())
                self._client.debug_text_world(str('Size: {}'.format(len(cluster))),
                                              cluster_position, color=Green(), size=18)

        for cluster in self.enemy_clusters:
            if cluster:
                radius = cluster.position.distance_to_furthest(cluster)
                cluster_position = cluster.position.to3
                cluster_position += Point3((0, 0, 6))
                self._client.debug_sphere_out(cluster_position, radius, color=Red())
                self._client.debug_text_world(str('Size: {}'.format(len(cluster))),
                                              cluster_position, color=Red(), size=18)

        await self._client.send_debug()

    def update_clusters(self):
        """
        Updates the position of k-means clusters we keep of units
        """

        types_to_exclude = const2.CHANGELING | {
            const.OVERLORD, const.CREEPTUMORBURROWED, const.CREEPTUMOR, const.SPINECRAWLERUPROOTED, const.LARVA,
            const.UnitTypeId.EGG}

        our_army = [u for u in self.unit_cache.values() if u.type_id not in types_to_exclude]
        enemy_army = [u for u in self.enemy_cache.values() if u.type_id not in types_to_exclude]

        if our_army:
            clustering.k_means_update(self.army_clusters, our_army)

        if enemy_army:
            clustering.k_means_update(self.enemy_clusters, enemy_army)

    def update_unit_caches(self):
        """
        Updates the friendly units and enemy units caches
        """

        # Update cached values and create new cached units
        for units, cache in zip((self.units, self.known_enemy_units),
                                (self.unit_cache, self.enemy_cache)):
            for unit in units:
                # If we already remember this unit
                cached_unit = cache.get(unit.tag)
                if cached_unit:
                    # Update cached unit health and shield
                    cached_unit.update(unit, self.state.effects)

                else:
                    new_cached_unit = unit_cache.UnitCached(unit)
                    cache[unit.tag] = new_cached_unit

        # Forget enemy cached units that have moved to a new location
        cached_enemy_tags_to_delete = set()
        for cached_unit in self.enemy_cache.values():
            position = cached_unit.position
            if self.is_visible(position):
                cached_unit_snapshot = self.known_enemy_units.find_by_tag(cached_unit.tag)
                if not cached_unit_snapshot:
                    cached_enemy_tags_to_delete.add(cached_unit.tag)
        for cached_tag in cached_enemy_tags_to_delete:
            del self.enemy_cache[cached_tag]

    def publish(self, manager, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Publish a message of message_type to all subscribers.
        """
        for subscriber in self._message_subscriptions[message_type]:
            # COMMENTED OUT BECAUSE I DON'T THINK IT'S NECESSARY... LOOK OUT FOR BUGS THOUGH.
            # if subscriber is not manager:
            subscriber.inbox(message_type, value)

    def subscribe(self, manager, message_type):
        """Subscribes a manager to a type of message"""
        self._message_subscriptions[message_type].append(manager)

    def unsubscribe(self, manager, message_type):
        """Unsubscribes a manager to a type of message"""
        self._message_subscriptions[message_type].remove(manager)

    def can_attack(self, unit, target):
        can = (unit.can_attack_ground and not target.is_flying) or \
              (unit.can_attack_air and target.is_flying) or \
              (unit.type_id == const.BANELING and not target.is_flying) or \
              (unit.type_id == const.LURKERMP and not target.is_flying)
        return can

    def get_expansion_positions(self) -> List[sc2.position.Point2]:
        """Returns our expansion positions in order from nearest to furthest"""
        expansions = self.expansion_locations.keys()
        expansion_positions = self.start_location.sort_by_distance(expansions)

        return expansion_positions

    def get_enemy_expansion_positions(self) -> List[sc2.position.Point2]:
        """Returns enemy expansion positions in order from their nearest to furthest"""

        enemy_start_location = self.enemy_start_location.position

        expansions = self.expansion_locations.keys()
        enemy_expansion_positions = enemy_start_location.sort_by_distance(expansions)

        return enemy_expansion_positions

    def get_enemy_natural_expansion(self) -> Union[None, sc2.position.Point2]:
        try:
            return self.get_enemy_expansion_positions()[1]
        except IndexError:
            return None

    def update_pixel_maps(self):
        """
        Creates pixel maps to be used later in the game.

        Includes:
          * self.blank_pixel_map: A blank pixel map
          * self.pathing_grid: Copy of self.game_info.pathing_grid with start location structures flood-filled

        Meant to be called on the first iteration of the game.
        """

        # Update Blank Pixel Map
        blank_pixel_map = copy.deepcopy(self.game_info.pathing_grid)

        utils.blank_out_pixel_map(blank_pixel_map)

        self.blank_pixel_map = blank_pixel_map

        # Update Pathing Grid
        pathing_grid = copy.deepcopy(self.game_info.pathing_grid)

        start_locations = [self.start_location] + self.enemy_start_locations
        start_locations = [loc.rounded for loc in start_locations]

        # Flood fill the start locations to eliminate the structures pathing block
        for start_location in start_locations:
            for p in pathing_grid.flood_fill(start_location, lambda x: x == 255):
                pathing_grid[p] = [0]

        self.pathing_grid = pathing_grid

    def update_shortest_path_to_enemy_start_location(self):
        """
        Updates the stored shortest path to the enemy start location
        """

        pathfinder = Pathfinder(self.pathing_grid)

        shortest_path = pathfinder.find_path(
            self.start_location.rounded, self.enemy_start_location.rounded)

        if shortest_path is None:
            self.shortest_path_to_enemy_start_location = None
        else:
            self.shortest_path_to_enemy_start_location = [p for p in shortest_path]

    def shortest_path_between_points(self, points: List[Point2],
                                     starting_from_first_point=True)-> List[Point2]:
        """
        Brute force travelling salesman problem.
        Not efficient but works for small numbers of points (less than 7)

        Given a list of points, finds the path between them with the shortest distance.
        If starting_from_first_point is True, then the path must start with the first
        point in `points`
        """

        if not len(points):
            return []

        paths = itertools.permutations(points)

        if starting_from_first_point:
            paths = filter(lambda p: p[0] == points[0], paths)

        paths = list(paths)

        lengths = []
        for path in paths:
            length = 0
            for point_i in range(len(path)):
                if point_i == len(path) - 1:
                    break

                point_1 = path[point_i]
                point_2 = path[point_i + 1]

                length += point_1.distance_to(point_2)

            lengths.append(length)

        shortest_i = 0
        shortest_length = math.inf
        i = 0
        for path, length in zip(paths, lengths):
            if length < shortest_length:
                shortest_i = i
                shortest_length = length
            i += 1

        shortest_path = paths[shortest_i]
        return shortest_path

    def get_path_around_ranges(self, units, point1: Point2, point2: Point2, path_step=2) -> List[Tuple[int, int]]:
        """
        Gets a path to `point` avoiding `units`

        TODO: This doesn't use `units` right now, and only works on enemies that attack air
        """

        # Make a copy of a blank pixel map to draw on
        pixel_map = copy.deepcopy(self.blank_pixel_map)

        # Get enemy units that can attack air
        enemy_units = [u.snapshot for u in self.enemy_cache.values() if u.can_attack_air]

        # Flood fill the pixel map with unit ranges
        utils.draw_unit_ranges(pixel_map, units)

        # Find the path
        pathfinder = Pathfinder(pixel_map)
        path = pathfinder.find_path(point1, point2)

        if not path:
            return None

        # Convert path to list and use only every path_step(2nd step by default)
        path: List[Point2] = [p for p in path][::path_step]

        return path

    async def get_open_expansions(self) -> List[Point2]:
        """Gets a sorted list of open expansions from the start location"""

        expansions = []

        start_p = self.pathable_start_location

        expansion_locations = self.expansion_locations.keys()

        sorted_expansions = await self.sort_pathing_distances_to(
            expansion_locations, start_p)

        for el in sorted_expansions:

            def is_near_to_expansion(t):
                return t.position.distance_to(el) < self.EXPANSION_GAP_THRESHOLD

            if any(map(is_near_to_expansion, self.townhalls)):
                # already taken
                continue

            d = await self._client.query_pathing(start_p, el)
            if d is None:
                continue

            expansions.append(el)

        return expansions

    async def sort_pathing_distances_to(self, l: List[Union[Point2, sc2.unit.Unit]],
                                        end_p: Union[Point2, sc2.unit.Unit]) -> List[Point2]:
        """
        Sorts each item in `l` based on its pathing distance from `end_p`

        :param l: List of units/points to sort distances from `end_p`
        :param end_p: Point/Unit to sort distances of each item in `l` from
        """

        # Zip the list together with the start point
        zipped_list = [[start_p, end_p] for start_p in l]

        distances = await self._client.query_pathings(zipped_list)

        zip_with_distances = zip(distances, l)
        zip_with_distances = sorted(zip_with_distances, key=(lambda dp: dp[0]))

        sorted_l = [p for d, p in zip_with_distances]

        return sorted_l

    def find_nearby_pathable_point(self, near: sc2.position.Point2) -> Union[None, sc2.position.Point2]:
        distance = 70
        placement_step = 5
        for distance in range(2, distance, 2):

            possible_positions = [sc2.position.Point2(p).offset(near).to2 for p in (
                [(dx, -distance) for dx in range(-distance, distance + 1, placement_step)] +
                [(dx, distance) for dx in range(-distance, distance + 1, placement_step)] +
                [(-distance, dy) for dy in range(-distance, distance + 1, placement_step)] +
                [(distance, dy) for dy in range(-distance, distance + 1, placement_step)]
            )]

            try:
                positions = [position for position in possible_positions
                             if self.in_pathing_grid(position)]
            except AssertionError:
                return None

            if positions:
                return min(positions, key=lambda p: p.distance_to(near))
            else:
                return None

    def points_between_points(self, p1: Point2, p2: Point2, point_count=6) -> Iterable[Point2]:
        """
        Returns a generator of points in a straight line between `p1` and `p2`.

        NOTE: Not guaranteed to return `point_counts`. Could be fewer by 1.
        """

        p1x = round(p1.x)
        p1y = round(p1.y)
        p2x = round(p2.x)
        p2y = round(p2.y)

        steps_x = -(p1x - p2x) / point_count
        steps_y = -(p1y - p2y) / point_count

        if steps_x and steps_y:
            return (Point2((x, y)) for x, y in zip(numpy.arange(p1x, p2x, steps_x), numpy.arange(p1y, p2y, steps_y)))
        return ()

    def rect_corners(self, rect):
        p1 = sc2.position.Point2((rect.x, rect.y))
        p2 = p1 + sc2.position.Point2((rect.width, 0))
        p3 = p1 + sc2.position.Point2((0, rect.height))
        p4 = p1 + sc2.position.Point2((rect.width, rect.height))

        return p1, p2, p3, p4

    def adjacent_corners(self, rect, corner: Point2) -> Tuple[Point2, Point2]:
        """
        Returns the points of the adjacent corners of the given point in a rec
        """
        corners = self.rect_corners(rect)
        corners = corner.sort_by_distance(corners)

        # The closest corner (corners[0]) is the corner itself.
        # Get second and third closest corners
        adjacents = (corners[1], corners[2])

        return adjacents

    def point_between_townhall_and_resources(self, townhall: Unit):
        nearest_minerals = self.state.mineral_field.closer_than(8, townhall.position)
        nearest_gas = self.state.vespene_geyser.closer_than(8, townhall.position)
        nearest_resources = nearest_minerals | nearest_gas

        if nearest_resources:
            return nearest_resources.center
        else:
            return townhall.position

    def has_midgame_tech(self) -> bool:
        midgame_tech = {const.UnitTypeId.ROACHWARREN, const.UnitTypeId.ROACHWARREN}

        return bool(self.units(midgame_tech))

    def unit_is_engaged(self, unit: Unit) -> bool:
        """
        Determines if a unit is currently attacking a specific unit
        """
        return unit.is_attacking and isinstance(unit.order_target, int)

    def unit_is_busy(self, unit: Unit) -> bool:
        """
        Determines if a unit is busy or if we can use him for another high-level
        command(like from the ForceManager)

        Logic:
          * If the unit is on pure move command then we don't want to
            interrupt him. He could be microing.
          * If the unit is attacking and has a unit as target, we don't want
            to interrupt his focus.
          * If the unit has a weapon cooldown, we assume he's in combat
        """
        return \
            unit.is_moving \
            or (unit.is_attacking and isinstance(unit.order_target, int)) \
            or unit.weapon_cooldown > 0

    def is_melee(self, unit: Unit) -> bool:
        return unit.ground_range < 1.5 and unit.can_attack_ground

    def health_percentage_adjusted(self, unit: Unit) -> float:
        """
        Adjusts unit's health based on its build progress.

        Structures in progress have less health than structures
        """
        if unit.is_structure and not unit.is_ready:
            return unit.health_percentage + unit.build_progress
        return unit.health_percentage

    def shield_percentage_adjusted(self, unit: Unit) -> float:
        """
        Adjusts unit's shield based on its build progress.
        """
        if unit.is_structure and not unit.is_ready:
            return unit.shield_percentage + unit.build_progress
        return unit.shield_percentage

    def splash_on_enemies(
            self,
            units: Units,
            action: Callable[[Unit, Unit], None],
            search_range: float,
            condition: Callable[[Unit], bool]=None,
            min_enemies=1,
            priorities: set=None) -> bool:
        """
        Performs function `action` on an enemy if enough nearby enemies are found
        that we can enact splash damage on.

        Usage: Banelings and Infestors(fungal growth) looking for optimal splash damage

        :param units: Units to use splash damage
        :param action: Function that takes two Units as inputs and does splash-related actions
        :param search_range: Max distance to apply search of enemies to
        :param condition: Optional condition function that takes an enemy unit and returns a boolean.
                          Can be used, for instance, to check if a unit is already fungalled
        :param min_enemies: Minimum enemies required near each other to take `action`
        :param priorities: Optional enemies to act on. Default is all enemies
        :return:
        """
        # Memorized mapping from {enemy_tag: count_of_nearby_enemy_priorities}
        nearby_enemy_priority_counts: Dict[int, int] = {}

        for unit in units:
            nearby_enemy_units = self.known_enemy_units.closer_than(search_range, unit)

            if priorities is None:
                nearby_enemy_priorities = nearby_enemy_units
            else:
                nearby_enemy_priorities = nearby_enemy_units.of_type(priorities)

            if nearby_enemy_priorities:
                # Get the nearby priority target with the most nearby priority targets around it

                greatest_count = 0
                greatest_i = 0
                for u_i in range(len(nearby_enemy_priorities)):
                    u = nearby_enemy_priorities[u_i]

                    # Skip this unit if conditional is false
                    if condition is not None and not condition(u):
                        continue

                    u_nearby_enemy_count = nearby_enemy_priority_counts.get(u.tag)

                    if u_nearby_enemy_count is None:
                        u_nearby_enemy_count = len(nearby_enemy_units.closer_than(3, u))
                        nearby_enemy_priority_counts[u.tag] = u_nearby_enemy_count

                    if u_nearby_enemy_count > greatest_count:
                        greatest_count = u_nearby_enemy_count
                        greatest_i = u_i

                greatest_priority = nearby_enemy_priorities[greatest_i]

                if greatest_count >= min_enemies:
                    # If the enemy has enough enemies around him, then call
                    # `action` on it
                    action(unit, greatest_priority)
                    return True
        return False

    def count_units_in_attack_range(self, units1, units2, ranged_only=False):
        """
        Counts the number of units1 that are in attack range of at least one unit in units2
        """
        count = 0
        for unit1 in units1:
            if ranged_only and self.is_melee(unit1):
                continue
            for unit2 in units2:
                if unit1.target_in_range(unit2):
                    count += 1
                    break
        return count

    def closest_and_most_damaged(self, unit_group, unit, priorities=None, can_attack=True):
        """
        Gets the unit from Unitgroup who is the closest to `unit` but also the most damaged.

        Formula: ((health + shield) / 2) * distance * (1 if in priorities. 2 if not in priorities)

        :param can_attack: If true, filters `unit_group` for those that `unit` can attack
        """

        if priorities is None:
            priorities = set()

        if can_attack:
            unit_group = [u for u in unit_group if self.can_attack(unit, u)]

        if not unit_group:
            return

        def metric(u):
            if u.shield_max > 0:
                health = (self.health_percentage_adjusted(u) + self.shield_percentage_adjusted(u)) // 2
            else:
                health = self.health_percentage_adjusted(u)

            # Multiply non-priorities value so we prefer priorities
            priority_bonus = 1 if u.type_id in priorities else 7

            # Multiply structure values so we prefer non-structures
            non_structure_bonus = 25 if u.is_structure else 1

            # Multiple neural parasited units so we prefer not to attack them
            # Commented out because sadly we cannot check if enemies have a buff :(
            # neural_parasite_bonus = 100 if u.has_buff(const.BuffId.NEURALPARASITE) else 1:

            return health * u.distance_to(unit) * priority_bonus * non_structure_bonus

        if isinstance(unit_group, sc2.units.Units):
            return unit_group.sorted(metric)[0]
        else:
            return sorted(unit_group, key=metric)[0]

    def strength_of(self, unit):
        """
        Returns the calculated standalone estimated strength of a unit
        """

        if unit.ground_dps > 0 and unit.air_dps <= 0:
            strength = unit.ground_dps
        elif unit.air_dps > 0 and unit.ground_dps <= 0:
            strength = unit.air_dps
        else:
            strength = (unit.ground_dps + unit.air_dps) / 2

        # Arbitrarily multiply strength by 2 if they are ranged
        # TODO: Make this better
        if unit.ground_range > 1 or unit.air_range > 1:
            strength *= 2

        return strength

    def adjusted_dps(self, unit: Unit) -> float:
        """
        Gets an average of a unit's dps, and returns alternative values if the
        unit doesn't have dps, but still does damage (like banelings)
        """

        default_dps = const2.DEFAULT_DPS_MAP.get(unit.type_id)
        if default_dps is not None:
            return default_dps

        if unit.ground_dps > 0 >= unit.air_dps:
            dps = unit.ground_dps
        elif unit.air_dps > 0 >= unit.ground_dps:
            dps = unit.air_dps
        else:
            dps = (unit.ground_dps + unit.air_dps) / 2

        return dps

    def relative_army_strength(
            self,
            units_1: Union[clustering.Cluster, sc2.units.Units],
            units_2: Union[clustering.Cluster, sc2.units.Units],
            ignore_workers=False,
            ignore_defensive_structures=False,
            ignore_height_difference=True,) -> float:
        """
        Returns a positive value if u1 is stronger, and negative if u2 is stronger.
        A value of +12 would be very good and a value of -12 would be very bad.

        Uses Lanchester's Law
        https://en.wikipedia.org/wiki/Lanchester%27s_laws
        """

        # Filter out structures that can't attack
        # Also filter out structures that can attack if `ignore_defensive_structures` is true
        # Also filter out workers if ignore_workers is True
        u1 = [u for u in units_1
              if (not u.is_structure or u.can_attack_ground or u.can_attack_air)
              and (not ignore_defensive_structures or u not in const2.DEFENSIVE_STRUCTURES)
              and (ignore_workers or u.type_id not in const2.WORKERS)]
        u2 = [u for u in units_2
              if (not u.is_structure or u.can_attack_ground or u.can_attack_air)
              and (not ignore_defensive_structures or u not in const2.DEFENSIVE_STRUCTURES)
              and (ignore_workers or u.type_id not in const2.WORKERS)]

        u1_melee = []
        u1_ranged = []
        for u in u1:
            if self.is_melee(u):
                # Melee
                u1_melee.append(u)
            elif u.type_id in const2.DEFAULT_DPS_MAP:
                # Spellcasters
                u1_ranged.append(u)
            else:
                # Ranged
                u1_ranged.append(u)

        u2_melee = []
        u2_ranged = []
        for u in u2:
            if self.is_melee(u):
                # Melee
                u2_melee.append(u)
            elif u.type_id in const2.DEFAULT_DPS_MAP:
                # Spellcasters
                u2_ranged.append(u)
            else:
                # Ranged
                u2_ranged.append(u)

        u1_melee_dps = sum(self.adjusted_dps(u) for u in u1_melee)
        u1_ranged_dps = sum(self.adjusted_dps(u) for u in u1_ranged)

        u2_melee_dps = sum(self.adjusted_dps(u) for u in u2_melee)
        u2_ranged_dps = sum(self.adjusted_dps(u) for u in u2_ranged)

        if u1_melee_dps == 0 and u1_ranged_dps == 0 and u2_melee_dps == 0 and u2_ranged_dps == 0:
            # Return 0 if there are no units with dps
            return 0

        def calc_health(u: Unit) -> int:
            return u.health + u.shield

        u1_health = sum(calc_health(u) for u in u1)
        u2_health = sum(calc_health(u) for u in u2)

        if u1_health == 0 and u2_health == 0:
            return 0
        if u1_health == 0 or not u1:
            return -len(u2)
        elif u2_health == 0 or not u2:
            return len(u1)

        u1_avg_health = u1_health / len(u1)
        u2_avg_health = u2_health / len(u2)

        u1_melee_avg_dps = u1_melee_dps / len(u1_melee) if u1_melee_dps else 0
        u1_ranged_avg_dps = u1_ranged_dps / len(u1_ranged) if u1_ranged else 0

        u2_melee_avg_dps = u2_melee_dps / len(u2_melee) if u2_melee_dps else 0
        u2_ranged_avg_dps = u2_ranged_dps / len(u2_ranged) if u2_ranged else 0

        if not ignore_height_difference:
            u1_avg_height = sum(u.position3d.z for u in u1) / len(u1)
            u2_avg_height = sum(u.position3d.z for u in u2) / len(u2)

            # Simulate high ground advantage with 1.5x ranged DPS
            if u1_avg_height * 0.85 > u2_avg_height:
                u1_ranged_avg_dps *= 1.5
            elif u2_avg_height * 0.85 > u1_avg_height:
                u2_ranged_avg_dps *= 1.5

        # How many enemy units are destroyed per second
        u1_loss_rate = (u1_melee_avg_dps + u1_ranged_avg_dps) / u2_avg_health
        u2_loss_rate = (u2_melee_avg_dps + u2_ranged_avg_dps) / u1_avg_health

        # Lanchesters law calls for an exponent of 2.
        # Use 1.2 to bias towards the linear law for melee
        # Use 1.5 for ranged
        power_m = 1.2
        power_r = 1.5

        u1_melee_powered = len(u1_melee) ** power_m
        u1_ranged_powered = len(u1_ranged) ** power_r

        u2_melee_powered = len(u2_melee) ** power_m
        u2_ranged_powered = len(u2_ranged) ** power_r

        u1_term = u1_loss_rate * (u1_melee_powered + u1_ranged_powered)
        u2_term = u2_loss_rate * (u2_melee_powered + u2_ranged_powered)

        if u1_term > u2_term:
            result = math.sqrt((u1_melee_powered + u1_ranged_powered) - u2_loss_rate / u1_loss_rate * (u2_melee_powered + u2_ranged_powered))
            return result
        elif u2_term > u1_term:
            result = math.sqrt((u2_melee_powered + u2_ranged_powered) - u1_loss_rate / u2_loss_rate * (u1_melee_powered + u1_ranged_powered))
            return -result

        return 0

    def moving_closer_to(self, unit, cache, point) -> bool:
        """
        Returns true if the unit has been moving closer to POINT over all of
        its recorded positions. The unit must be represented in `cache` or
        False will be returned.

        """
        unit_cached = cache.get(unit.tag)
        if unit_cached:
            last_positions = unit_cached.last_positions

            # Only consider units we've seen their last position of
            if len(last_positions) == unit_cached.last_positions_maxlen:
                # If every point in the units last positions are closer to our start location, then
                # add one to the closer_enemy_counts
                last_position_2 = last_positions[0]
                for last_position_i in range(1, len(last_positions)):
                    last_position = last_positions[last_position_i]
                    if last_position_2.distance_to(point) <= \
                            last_position.distance_to(point):
                        break
                    last_position_2 = last_position
                else:
                    return True

        return False
