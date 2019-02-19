from typing import Union
import math

from lib.sc2.unit import Unit
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

