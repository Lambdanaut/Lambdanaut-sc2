import enum
from typing import Dict, List, Union

from sc2.constants import *

# A good basic macro opener. Always start here
EARLY_GAME_DEFAULT_OPENER = [
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    DRONE,  # 13
    OVERLORD,  # 2
    DRONE,  # 14
    DRONE,  # 15
    DRONE,  # 16
    DRONE,  # 17
    DRONE,  # 18
]

# Get a spawning pool first with Zerglings and a Spine Crawler
EARLY_GAME_POOL_FIRST_DEFENSIVE = [
    SPAWNINGPOOL,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    SPINECRAWLER,
    ZERGLING, ZERGLING,
    QUEEN,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
]

# Get a spawning pool first with Zerglings for an all-in rush
EARLY_GAME_POOL_FIRST_OFFENSIVE = [
    EXTRACTOR,
    SPAWNINGPOOL,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    SPINECRAWLER,
    ZERGLING, ZERGLING,
    QUEEN,
    ZERGLINGMOVEMENTSPEED,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
]

# Get a hatchery first with 4 defensive Zerglings
EARLY_GAME_HATCHERY_FIRST = [
    HATCHERY,  # 2 (First expand)
    DRONE,  # 19
    EXTRACTOR,  # 1
    SPAWNINGPOOL,
    DRONE, DRONE, DRONE,  # 22
    OVERLORD,  # 3
    QUEEN,  # 1
    QUEEN,  # 2
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,  # 4
]

# Get a ling-bane composition for early attacks and then into mutas
MID_GAME_LING_BANE_MUTA = [
    ZERGLINGMOVEMENTSPEED,
    DRONE, DRONE, DRONE, DRONE,
    HATCHERY,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE,
    EXTRACTOR,
    DRONE, DRONE, DRONE,
    QUEEN,
    BANELINGNEST,
    EXTRACTOR,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE,
    BANELING, BANELING, ZERGLING, ZERGLING,
    EXTRACTOR,
    DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,
    LAIR,

]
MID_GAME_LING_BANE_MUTA += ([ZERGLING] * 11 + [BANELING] * 5) * 2
MID_GAME_LING_BANE_MUTA += [
    EXTRACTOR,
    HATCHERY,
    EXTRACTOR, EXTRACTOR,
    QUEEN,
    CENTRIFICALHOOKS,
    SPIRE,
]
MID_GAME_LING_BANE_MUTA += ([ZERGLING] * 4 + [BANELING] * 2) * 1
MID_GAME_LING_BANE_MUTA += [MUTALISK] * 20

MID_GAME_ROACH_TIMING_ATTACK = []

MID_GAME_ROACH_HYDRA_LURKER = []


class Builds(enum.Enum):
    """Build Types"""

    DEFAULT = 0  # Used in the BUILD_TREE to set the default next-build

    EARLY_GAME_DEFAULT_OPENER = 1
    EARLY_GAME_POOL_FIRST_DEFENSIVE = 2
    EARLY_GAME_POOL_FIRST_OFFENSIVE = 3
    EARLY_GAME_HATCHERY_FIRST = 4

    MID_GAME_LING_BANE_MUTA = 5
    MID_GAME_ROACH_TIMING_ATTACK = 6
    MID_GAME_ROACH_HYDRA_LURKER = 7


# Mapping from Build Type to Build Targets list
BUILD_MAPPING = {
    Builds.EARLY_GAME_DEFAULT_OPENER: EARLY_GAME_DEFAULT_OPENER,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_HATCHERY_FIRST: EARLY_GAME_HATCHERY_FIRST,

    Builds.MID_GAME_LING_BANE_MUTA: MID_GAME_LING_BANE_MUTA,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: MID_GAME_ROACH_HYDRA_LURKER,
}

# Mapping of build to default next build
# The default build is switched to if the build is at its end
DEFAULT_NEXT_BUILDS = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.MID_GAME_LING_BANE_MUTA: None,
    Builds.MID_GAME_ROACH_TIMING_ATTACK: None,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: None,
}

# ### UNUSED CODE. DECIDED FOR A DIFFERENT STRATEGY (Decision via message passing) ###
# Decision tree to figure out next build options
# If a value is "None", then backout and follow another link through the tree
# BUILD_TREE = {
#     Builds.EARLY_GAME_DEFAULT_OPENER: {
#         Builds.DEFAULT: Builds.EARLY_GAME_HATCHERY_FIRST,
#
#         Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: None,
#         Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: None,
#         Builds.EARLY_GAME_HATCHERY_FIRST: {
#             Builds.DEFAULT: Builds.MID_GAME_LING_BANE_MUTA,
#
#             Builds.MID_GAME_LING_BANE_MUTA: None,
#             Builds.MID_GAME_ROACH_TIMING_ATTACK: None,
#             Builds.MID_GAME_ROACH_HYDRA_LURKER: None,
#         },
#     }
# }
#
# def traverse_build_tree(build_indexes: List[Builds], build_tree) -> Union[None, Dict]:
#     """
#     Given a list of tree indexes and a build tree to traverse, traverses the
#     tree through each build index to get the value at the end
#     """
#
#     build = build_indexes[0]
#
#     rest_of_tree = build_tree[build]
#
#     if len(build_indexes) == 1:
#         return rest_of_tree
#
#     return traverse_build_tree(build_indexes[1:], rest_of_tree)
#

