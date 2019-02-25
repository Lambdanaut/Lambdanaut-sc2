from typing import Callable, Iterable, List, Set, Tuple, Union
import math

from lib.sc2.unit import Unit
from lib.sc2.pixel_map import PixelMap
from lib.sc2.position import Point2


def ramp_point_nearest_point(ramps, p):
    # UNUSED RIGHT NOW
    for ramp in ramps:
        ramp_point = ramp.bottom_center

        return p.closest(ramp_point)


def towards_direction(p: Union[Unit, Point2], direction: Union[int, float], distance: Union[int, float]):
    """
    Gets a point `distance` away from `p` at the angle given by "direction" in radians

    Uses trigonometry:
    https://www.mathwarehouse.com/trigonometry/sine-cosine-tangent-practice3.php
    """

    p = p.position

    hypotenuse_length = distance
    opposite_length = hypotenuse_length * math.sin(direction)
    adjacent_length = math.sqrt(hypotenuse_length**2 - opposite_length**2)

    new_p = p + Point2((adjacent_length, opposite_length))

    return new_p


def blank_out_pixel_map(pixel_map: PixelMap, value=0x0):
    """
    Fllod fills an entire pixel map with `value`
    :param pixel_map: pixel map to mutate
    :param value: value to flood entire map with
    """
    for y in range(pixel_map.height):
        for x in range(pixel_map.width):
            pixel_map[(x, y)] = [value]


def flood_fill_(pixel_map: PixelMap, start_point: Point2, pred: Callable[[int], bool]) -> Set[Point2]:
    """
    Just like PixelMap.flood_fill, except it doesn't fill in if diagonals are empty.
    """
    nodes: Set[Point2] = set()
    queue: List[Point2] = [start_point]

    while queue:
        x, y = queue.pop()

        if not (0 <= x < pixel_map.width and 0 <= y < pixel_map.height):
            continue

        if Point2((x, y)) in nodes:
            continue

        if pred(pixel_map[x, y]):
            nodes.add(Point2((x, y)))
            for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                queue.append(Point2((x + a, y + b)))

    return nodes


def draw_circle(pixel_map: PixelMap, center: Point2, radius: int, val=0xFF):
    """
    Flood fills a circle in a pixel_map

    :param pixel_map: Pixel map to mutate
    :param center: Center point of circle
    :param radius: Radius of circle
    :param val: Value to flood with
    """

    x0, y0 = center
    f = 1 - radius
    ddf_x = 1
    ddf_y = -2 * radius
    x = 0
    y = radius

    try:
        # Set top, left, bottom, and right-most pixels
        pixel_map[(x0, y0 + radius)] = [val]
        pixel_map[(x0, y0 - radius)] = [val]
        pixel_map[(x0 + radius, y0)] = [val]
        pixel_map[(x0 - radius, y0)] = [val]

        while x < y:
            if f >= 0:
                y -= 1
                ddf_y += 2
                f += ddf_y
            x += 1
            ddf_x += 2
            f += ddf_x

            # Set pixels
            pixel_map[(x0 + x, y0 + y)] = [val]
            pixel_map[(x0 - x, y0 + y)] = [val]
            pixel_map[(x0 + x, y0 - y)] = [val]
            pixel_map[(x0 - x, y0 - y)] = [val]
            pixel_map[(x0 + y, y0 + x)] = [val]
            pixel_map[(x0 - y, y0 + x)] = [val]
            pixel_map[(x0 + y, y0 - x)] = [val]
            pixel_map[(x0 - y, y0 - x)] = [val]

    except:
        # If the range goes outside the pixelmap, just return with no change
        # TODO: Flood fill to the edge of the pixelmap and stop there without breaking
        print("Flood filled to the edge of a pixelmap. Returning with no change. ")

    for p in flood_fill_(pixel_map, center, lambda v: v != val):
        pixel_map[p] = [val]


def draw_unit_ranges(pixel_map, units):
    """
    Draws unit ranges. Only works with air ranges at the moment.
    """
    # Iterable of tuples ((unit position, unit air range))
    enemy_ranges: Iterable[Tuple[Point2, int]] = \
        ((u.position.rounded, round(u.air_range * 1.15))
         for u in units)

    # Flood fill the pixel map with enemy unit ranges
    for pos, air_range in enemy_ranges:
        draw_circle(pixel_map, pos, air_range, val=0xFF)
