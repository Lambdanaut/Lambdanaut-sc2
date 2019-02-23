from typing import Iterator, List, Tuple

from lib.astar import AStar
from lib.sc2.pixel_map import PixelMap
from lib.sc2.position import Point2


class Pathfinder(AStar):
    """
    Uses a pathfinding algorithm to traverse a pixel map
    """

    def __init__(self, pixel_map: PixelMap):
        super(AStar, self).__init__()

        # Pixel map to traverse
        self.pixel_map: PixelMap = pixel_map

    def find_path(self, start: Tuple[int, int], goal: Tuple[int, int]) -> Iterator[Tuple[int, int]]:
        """
        Returns a path from start to goal
        """
        path = self.astar(start, goal)
        return None if path is None else (Point2(p) for p in path)

    def heuristic_cost_estimate(self, current: Tuple[int, int], goal: Tuple[int, int]):
        p1 = Point2(current)
        p2 = Point2(goal)

        return p1.distance_to(p2)

    def distance_between(self, n1: Tuple[int, int], n2: Tuple[int, int]):
        """
        Returns the distance between two adjacent nodes
        """
        x1, y1 = n1
        x2, y2 = n2

        if x1 == x2 or y1 == y2:
            # Nodes are adjacent horizontally or vertically. Return 1
            return 1
        else:
            # Nodes are adjacent diagonally. Return 1.4142 (Hypotenuse of a 1x1 right triangle)
            return 1.4142

    def neighbors(self, node: Tuple[int, int]):
        """
        Gets the nearest neighbors for a node

        If we're in a node that's unpathable, act like its neighbors are pathable.
        """
        x, y = node

        # Horizontal, vertical, and diagonal neighbors
        nodes = [(x, y-1), (x, y+1), (x-1, y), (x+1, y),
                          (x+1, y+1), (x+1, y-1), (x-1, y+1), (x-1, y-1)]

        if self.pixel_map.is_empty(node):
            # Filter for nodes that aren't set
            nodes = [(nx, ny) for nx, ny in nodes
                     if 0 <= nx < self.pixel_map.width
                     and 0 <= ny < self.pixel_map.height
                     and self.pixel_map.is_empty((nx, ny))]

        return nodes

    def print_path(self, path: List[Tuple[int, int]]):
        """
        Given a path as a list, prints it out on the pixel_map
        """
        for y in range(self.pixel_map.height):
            for x in range(self.pixel_map.width):
                if self.pixel_map.is_set((x, y)):
                    print("#", end="")
                elif (x, y) in path:
                    print("*", end="")
                else:
                    print(" ", end="")
            print("")
