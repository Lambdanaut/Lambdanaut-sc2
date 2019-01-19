import enum

import sc2
from sc2.constants import *


class AtLeast(object):
    """
    Container object for use in builds

    Functionally it means that we want to have built at least `N` of `unit_type`
    at this point in the build.

    Example that will ensure we have at least one Spire at this point:
        BUILD = [
            AtLeast(1, Spire),
            MUTALISK,
            MUTALISK,
        ]
    """
    def __init__(self, n, unit_type):
        self.n = n
        self.unit_type = unit_type


class IfHasThenBuild(object):
    """
    Container object for use in builds

    Functionally it means that if we have at least 1 units of
    `conditional_unit_type`, then add `n` `unit_type` to the the build order.

    Example that will build 10 banelings if we have a banelings nest
        BUILD = [
            IfHasThenBuild(BANELINGNEST, BANELING, 10),
        ]
    """
    def __init__(self, conditional_unit_type, unit_type,  n=1):
        self.conditional_unit_type = conditional_unit_type
        self.unit_type = unit_type
        self.n = n


class OneForEach(object):
    """
    Container object for use in builds

    Functionally it means that for each `for_each_unit_type` we have built,
    add on a `unit_type` to the build queue.

    Example that will build a baneling for each Zergling with have. If we
    have 5 zerglings, build 5 banelings.
        BUILD = [
            OneForEach(BANELING, ZERGLING),
        ]
    """
    def __init__(self, unit_type, for_each_unit_type):
        self.for_each_unit_type = for_each_unit_type
        self.unit_type = unit_type


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
    ZERGLING, ZERGLING, ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    QUEEN,
    QUEEN,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE,
    SPINECRAWLER,
]

# Enemy cheese found. Get a spawning pool first with Zerglings and Spine Crawlers
EARLY_GAME_POOL_FIRST_DEFENSIVE = [
    SPAWNINGPOOL,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    QUEEN,
    SPINECRAWLER,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    SPINECRAWLER,
    ZERGLING, ZERGLING,
    SPINECRAWLER,
    ZERGLING, ZERGLING,
    QUEEN,
    HATCHERY,
    EXTRACTOR,
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
    HATCHERY,
]

# Seen enemy air units / air tech (Banshees, Mutas, Liberators, Oracle...)
EARLY_GAME_SPORE_CRAWLERS = [
    HATCHERY,  # 2 (First expand)
    DRONE,  # 19
    EXTRACTOR,  # 1
    SPAWNINGPOOL,
    DRONE, DRONE, DRONE,  # 22
    OVERLORD,  # 3
    QUEEN,  # 1
    QUEEN,  # 2
    OneForEach(SPORECRAWLER, HATCHERY),  # One Spore Crawler for each Hatchery we own
]

# Get a hatchery first with 4 defensive Zerglings
EARLY_GAME_HATCHERY_FIRST = [
    HATCHERY,  # 2 (First expand)
    DRONE,  # 19
    EXTRACTOR,  # 1
    SPAWNINGPOOL,
    DRONE, DRONE, # 21
    OVERLORD,  # 3
    QUEEN,  # 1
    ZERGLINGMOVEMENTSPEED,
    ZERGLING, ZERGLING,
    QUEEN,  # 2
    ZERGLING, ZERGLING,  # 4
]

# Get a ling-bane composition for early attacks and then into mutas
MID_GAME_LING_BANE_MUTA = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    HATCHERY,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    BANELINGNEST,
    EXTRACTOR,
    EVOLUTIONCHAMBER,
    DRONE, DRONE,
    QUEEN,
    EVOLUTIONCHAMBER,
    EXTRACTOR,
    DRONE, DRONE,
    ZERGMELEEWEAPONSLEVEL1,
    ZERGGROUNDARMORSLEVEL1,
    ZERGLING, ZERGLING, BANELING, BANELING,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,
]
MID_GAME_LING_BANE_MUTA += ([ZERGLING] * 24 + [BANELING] * 10) * 2
MID_GAME_LING_BANE_MUTA += [
    DRONE, DRONE, DRONE, DRONE,
    LAIR,
    HATCHERY,
    BURROW,
    QUEEN,
    OVERSEER,
    EXTRACTOR,
    CENTRIFICALHOOKS,
    ZERGMELEEWEAPONSLEVEL2,
    ZERGGROUNDARMORSLEVEL2,
    SPIRE,
    EXTRACTOR,
    EXTRACTOR,
]
MID_GAME_LING_BANE_MUTA += [MUTALISK] * 5
MID_GAME_LING_BANE_MUTA += [INFESTATIONPIT]
MID_GAME_LING_BANE_MUTA += [ZERGFLYERWEAPONSLEVEL1]
MID_GAME_LING_BANE_MUTA += [CORRUPTOR] * 1
# MID_GAME_LING_BANE_MUTA += [INFESTOR] * 2
MID_GAME_LING_BANE_MUTA += [OVERSEER] * 1
MID_GAME_LING_BANE_MUTA += [MUTALISK] * 4
MID_GAME_LING_BANE_MUTA += [ZERGFLYERWEAPONSLEVEL2]


MID_GAME_ROACH_HYDRA_LURKER = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    HATCHERY,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    HATCHERY,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    EVOLUTIONCHAMBER,
    EVOLUTIONCHAMBER,
    IfHasThenBuild(BANELINGNEST, ZERGLING, 24),
    IfHasThenBuild(BANELINGNEST, BANELING, 10),
    ROACHWARREN,
    EXTRACTOR,
    DRONE, DRONE,
    EXTRACTOR,
    DRONE, DRONE,
    EXTRACTOR,
    DRONE,
    ZERGMISSILEWEAPONSLEVEL1,
    EXTRACTOR,
    ZERGGROUNDARMORSLEVEL1,
    DRONE,
    EXTRACTOR,
    DRONE,
    ROACH,
    ROACH,
    LAIR,
    ROACH,
    BURROW,
]
MID_GAME_ROACH_HYDRA_LURKER += [ROACH] * 13
MID_GAME_ROACH_HYDRA_LURKER += [RAVAGER] * 2
MID_GAME_ROACH_HYDRA_LURKER += [GLIALRECONSTITUTION]
MID_GAME_ROACH_HYDRA_LURKER += [RAVAGER] * 3
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISKDEN]
MID_GAME_ROACH_HYDRA_LURKER += [
    OVERSEER,
    ZERGMISSILEWEAPONSLEVEL2,
    ZERGGROUNDARMORSLEVEL2,
    EVOLVEGROOVEDSPINES,
]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 5
MID_GAME_ROACH_HYDRA_LURKER += [INFESTATIONPIT]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 2
MID_GAME_ROACH_HYDRA_LURKER += [HATCHERY]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 3
MID_GAME_ROACH_HYDRA_LURKER += [EXTRACTOR]
MID_GAME_ROACH_HYDRA_LURKER += [OVERSEER, QUEEN] * 1
MID_GAME_ROACH_HYDRA_LURKER += [EVOLVEMUSCULARAUGMENTS]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 5
MID_GAME_ROACH_HYDRA_LURKER += [EXTRACTOR]


LATE_GAME_CORRUPTOR_BROOD_LORD = [
    AtLeast(1, INFESTATIONPIT),
    AtLeast(1, SPIRE),  # ASSUMES SPIRE EXISTS
    AtLeast(1, HIVE),
    GREATERSPIRE,
    CORRUPTOR, CORRUPTOR, CORRUPTOR, CORRUPTOR, CORRUPTOR,
    AtLeast(5, HATCHERY),
    # Get late game upgrades
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGLINGATTACKSPEED),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGMELEEWEAPONSLEVEL3),
    AtLeast(1, ZERGFLYERWEAPONSLEVEL1),
]
LATE_GAME_CORRUPTOR_BROOD_LORD += [BROODLORD] * 10
LATE_GAME_CORRUPTOR_BROOD_LORD += [
    AtLeast(1, ZERGFLYERWEAPONSLEVEL2)]



class Builds(enum.Enum):
    """Build Types"""

    EARLY_GAME_DEFAULT_OPENER = 0

    EARLY_GAME_POOL_FIRST_CAUTIOUS = 1
    EARLY_GAME_POOL_FIRST_DEFENSIVE = 2
    EARLY_GAME_POOL_FIRST_OFFENSIVE = 3
    EARLY_GAME_HATCHERY_FIRST = 4
    EARLY_GAME_SPORE_CRAWLERS = 5

    MID_GAME_LING_BANE_MUTA = 6
    MID_GAME_ROACH_HYDRA_LURKER = 7

    LATE_GAME_CORRUPTOR_BROOD_LORD = 8


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
    Builds.EARLY_GAME_SPORE_CRAWLERS,
}

MID_GAME_BUILDS = {
    Builds.MID_GAME_LING_BANE_MUTA,
    Builds.MID_GAME_ROACH_HYDRA_LURKER,
}

LATE_GAME_BUILDS = {
    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
}

# Maps Build Stages to Builds in those stages
BUILD_STAGE_MAPPING = {
    BuildStages.OPENING: OPENER_BUILDS,
    BuildStages.EARLY_GAME: EARLY_GAME_BUILDS,
    BuildStages.MID_GAME: MID_GAME_BUILDS,
    BuildStages.LATE_GAME: LATE_GAME_BUILDS,
}


def get_build_stage(build: Builds):
    """
    Helper function to get the build stage of a build
    (Opening, Early Game, Mid Game, or Late Game)
    """
    for build_stage, builds in BUILD_STAGE_MAPPING.items():
        if build in builds:
            return build_stage


# Mapping from Build Type to Build Targets list
BUILD_MAPPING = {
    Builds.EARLY_GAME_DEFAULT_OPENER: EARLY_GAME_DEFAULT_OPENER,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_SPORE_CRAWLERS: EARLY_GAME_SPORE_CRAWLERS,
    Builds.EARLY_GAME_HATCHERY_FIRST: EARLY_GAME_HATCHERY_FIRST,

    Builds.MID_GAME_LING_BANE_MUTA: MID_GAME_LING_BANE_MUTA,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: MID_GAME_ROACH_HYDRA_LURKER,

    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: LATE_GAME_CORRUPTOR_BROOD_LORD,
}

# Mapping of build to default next build
# The default build is switched to if the build is at its end
DEFAULT_NEXT_BUILDS = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_LING_BANE_MUTA: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: None,
}

# Changes to default build if enemy is terran
DEFAULT_NEXT_BUILDS_TERRAN = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_LING_BANE_MUTA,
}
DEFAULT_NEXT_BUILDS_ZERG = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE_MUTA,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_LING_BANE_MUTA,
}
DEFAULT_NEXT_BUILDS_PROTOSS = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
}


def update_default_builds(enemy_race):
    """Based on the enemy's race, we change the default builds"""
    if enemy_race == sc2.Race.Terran:
        DEFAULT_NEXT_BUILDS.update(DEFAULT_NEXT_BUILDS_TERRAN)
    elif enemy_race == sc2.Race.Zerg:
        DEFAULT_NEXT_BUILDS.update(DEFAULT_NEXT_BUILDS_ZERG)
    elif enemy_race == sc2.Race.Protoss:
        DEFAULT_NEXT_BUILDS.update(DEFAULT_NEXT_BUILDS_PROTOSS)


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

