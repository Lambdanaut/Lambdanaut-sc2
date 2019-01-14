import enum

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

# Suspect enemy cheese but no proof. Get a spawning pool first with Zerglings
EARLY_GAME_POOL_FIRST_CAUTIOUS = [
    SPAWNINGPOOL,
    HATCHERY,
    EXTRACTOR,
    DRONE,
    OVERLORD,  # 3
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    QUEEN,
    QUEEN,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE,
]

# Enemy cheese found. Get a spawning pool first with Zerglings and a Spine Crawler
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
    DRONE, DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,
    QUEEN,
    BANELINGNEST,
    EVOLUTIONCHAMBER,
    EVOLUTIONCHAMBER,
    EXTRACTOR,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE,
    ZERGMELEEWEAPONSLEVEL1,
    ZERGGROUNDARMORSLEVEL1,
    ZERGLING, ZERGLING, BANELING, BANELING,
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
    ZERGMELEEWEAPONSLEVEL2,
    ZERGGROUNDARMORSLEVEL2,
]
MID_GAME_LING_BANE_MUTA += ([ZERGLING] * 6 + [BANELING] * 2) * 1
MID_GAME_LING_BANE_MUTA += [MUTALISK] * 5
MID_GAME_LING_BANE_MUTA += [ZERGFLYERWEAPONSLEVEL1]
MID_GAME_LING_BANE_MUTA += [MUTALISK] * 10
MID_GAME_LING_BANE_MUTA += [ZERGFLYERWEAPONSLEVEL2]
MID_GAME_LING_BANE_MUTA += ([ZERGLING] * 4 + [BANELING] * 2) * 1

MID_GAME_ROACH_TIMING_ATTACK = []

MID_GAME_ROACH_HYDRA_LURKER = []


class Builds(enum.Enum):
    """Build Types"""

    EARLY_GAME_DEFAULT_OPENER = 0

    EARLY_GAME_POOL_FIRST_CAUTIOUS = 1
    EARLY_GAME_POOL_FIRST_DEFENSIVE = 2
    EARLY_GAME_POOL_FIRST_OFFENSIVE = 3
    EARLY_GAME_HATCHERY_FIRST = 4

    MID_GAME_LING_BANE_MUTA = 5
    MID_GAME_ROACH_TIMING_ATTACK = 6
    MID_GAME_ROACH_HYDRA_LURKER = 7


class BuildStages(enum.Enum):
    """Stages of the game"""
    OPENING = 0
    EARLY_GAME = 1
    MID_GAME = 2
    LATE_GAME = 3


OPENER_BUILDS = {
    Builds.EARLY_GAME_DEFAULT_OPENER,
}

EARLY_GAME_BUILDS = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_HATCHERY_FIRST,
}

MID_GAME_BUILDS = {
    Builds.MID_GAME_LING_BANE_MUTA,
    Builds.MID_GAME_ROACH_TIMING_ATTACK,
    Builds.MID_GAME_ROACH_HYDRA_LURKER,
}

LATE_GAME_BUILDS = {

}

# Maps Build Stages to Builds in those stages
BUILD_STAGE_MAPPING = {
    BuildStages.OPENING: OPENER_BUILDS,
    BuildStages.EARLY_GAME: EARLY_GAME_BUILDS,
    BuildStages.MID_GAME: MID_GAME_BUILDS,
    BuildStages.LATE_GAME: LATE_GAME_BUILDS,
}


def get_build_stage(build: Builds) -> BuildStages:
    """
    Helper function to get the build stage of a build
    (Opening, Early Game, Mid Game, or Late Game)
    """
    for build_stage, builds in BUILD_STAGE_MAPPING:
        if build in builds:
            return build_stage


# Mapping from Build Type to Build Targets list
BUILD_MAPPING = {
    Builds.EARLY_GAME_DEFAULT_OPENER: EARLY_GAME_DEFAULT_OPENER,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: EARLY_GAME_POOL_FIRST_CAUTIOUS,
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
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
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

