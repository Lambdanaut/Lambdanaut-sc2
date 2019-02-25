import uuid

import lib.sc2 as sc2
from lib.sc2.constants import *

from lambdanaut.const2 import Messages


class SpecialBuildTarget(object):
    def __init__(self):
        self.id = uuid.uuid4()

    def extract_unit_type(self):
        """
        Gets the unit type from this special container
        """
        return self.unit_type


class AtLeast(SpecialBuildTarget):
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
        super(AtLeast, self).__init__()

        self.n = n
        self.unit_type = unit_type


class IfHasThenBuild(SpecialBuildTarget):
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
        super(IfHasThenBuild, self).__init__()

        self.conditional_unit_type = conditional_unit_type
        self.unit_type = unit_type
        self.n = n


class IfHasThenDontBuild(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that if we don't have any units of type
    `conditional_unit_type`, then add `n` `unit_type` to the the build order.

    Example that will build 10 banelings if we have a banelings nest
        BUILD = [
            IfHasThenBuild(BANELINGNEST, BANELING, 10),
        ]
    """
    def __init__(self, conditional_unit_type, unit_type,  n=1):
        super(IfHasThenDontBuild, self).__init__()

        self.conditional_unit_type = conditional_unit_type
        self.unit_type = unit_type
        self.n = n


class OneForEach(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that for each `for_each_unit_type` we have built,
    add on a `unit_type` to the build queue.

    NOTE: This checks on units we've created that are finished and ready.
          An in-construction hatchery doesn't count.
          Also, `for_each_unit_type` MUST be a UnitTypeId. No Upgrades.

    Example that will build a baneling for each Zergling with have. If we
    have 5 zerglings, build 5 banelings.
        BUILD = [
            OneForEach(BANELING, ZERGLING),
        ]
    """
    def __init__(self, unit_type, for_each_unit_type):
        super(OneForEach, self).__init__()

        self.for_each_unit_type: UnitTypeId = for_each_unit_type
        self.unit_type = unit_type


class CanAfford(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that if we can afford `unit_type`, we add it to the
    build queue.

    Example that will upgrade Zergling Speed if we can afford it, otherwise
    continues building zerglings
        BUILD = [
            CanAfford(ZERGLINGMOVEMENTSPEED),
            ZERGLING,
            ZERGLING,
        ]
    """
    def __init__(self, unit_type):
        super(CanAfford, self).__init__()

        self.unit_type = unit_type


class PullWorkersOffVespeneUntil(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means to only mine each geyser with `n` vespene workers
    until `unit_type` is constructed

    NOTE: Cannot be wrapped recursively.
    This is not valid: `PullWorkersOffVespeneUntil(AtLeast(1, ZERGLING))`

    Example that will only mine with 2 gas workers per geyser until a Roach
    is constructed.
        BUILD = [
            PullWorkersOffVespeneUntil(ROACH, n=2),
            ZERGLING,
            ZERGLING,
            ROACH,  # Put 3 workers back on vespene at this point
        ]
    """
    def __init__(self, unit_type, n=0):
        super(PullWorkersOffVespeneUntil, self).__init__()

        self.unit_type = unit_type
        self.n = n


class PublishMessage(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that we publish the message `message_type` with
    optional value `value` the first time we reach this point in the build.

    NOTE: Cannot be wrapped recursively.
    This is not valid: `PublishMessage(AtLeast(1, ZERGLING))`

    Example that will publish a message to sent the second overlord to the
    enemy's main ramp

        BUILD = [
            PublishMessage(Messages., n=2),
        ]
    """
    def __init__(self, message, value=None):
        super(PublishMessage, self).__init__()

        self.unit_type = None
        self.message = message
        self.value = value


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

# Ravager all-in with no transition
RAVAGER_ALL_IN = [
    PublishMessage(Messages.DONT_DEFEND),  # Publish a message saying we shouldn't switch to DEFENDING
    PullWorkersOffVespeneUntil(ROACH, n=2),  # Mine with only 2 workers until we have a roach
    PublishMessage(Messages.OVERLORD_SCOUT_2_TO_ENEMY_RAMP),  # Send the second overlord to the enemy's main ramp
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    DRONE,  # 13
    DRONE,  # 14
    SPAWNINGPOOL,
    EXTRACTOR,  # 1
    OVERLORD,  # 2
    EXTRACTOR, # 2
    ZERGLING, ZERGLING,  # 15
    OVERLORD,  # 3
    ROACHWARREN,
    ROACH,
    ROACH,
    IfHasThenDontBuild(RAVAGER, ROACH, 2),
    RAVAGER, RAVAGER, RAVAGER,
    RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    QUEEN,
]
RAVAGER_ALL_IN += [RAVAGER] * 100


# Open with 3 ravagers and then transition into another build
def opener_ravager_harass_when_to_stop_attacking(manager) -> bool:
    """
    Conditional function that returns True when
     * we have at least 3 hatcheries or
     * or if we have 2 hatcheries and no ravagers left
    """
    hatch_len = len(manager.bot.units(HATCHERY).ready)
    return hatch_len > 2 \
        or (hatch_len > 1 and len(manager.bot.units(RAVAGER)) == 0 and len(manager.bot.units(RAVAGERCOCOON)) == 0)


OPENER_RAVAGER_HARASS = [
    PullWorkersOffVespeneUntil(ROACH, n=2),  # Mine with only 2 workers until we have a roach
    PublishMessage(Messages.OVERLORD_SCOUT_2_TO_ENEMY_RAMP),  # Send the second overlord to the enemy's main ramp
    # Start attacking and don't stop until we have no ravagers left
    PublishMessage(Messages.DONT_STOP_ATTACKING_UNTIL_CONDITION, opener_ravager_harass_when_to_stop_attacking),
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    DRONE,  # 13
    DRONE,  # 14
    SPAWNINGPOOL,
    EXTRACTOR,  # 1
    OVERLORD,  # 2
    EXTRACTOR,  # 2
    OVERLORD,  # 3
    OVERLORD,  # 4  ( Get an extra in case we lose our aggressive overlords)
    ROACHWARREN,
    ROACH,
    IfHasThenDontBuild(RAVAGER, ROACH, 3),
    RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    # Pull workers off vespene for 60 seconds
    PublishMessage(Messages.PULL_WORKERS_OFF_VESPENE_FOR_X_SECONDS, 60),
    QUEEN,
    DRONE, DRONE, DRONE, DRONE # 18
]

# Suspect enemy cheese but no proof. Get a spawning pool first with Zerglings
EARLY_GAME_POOL_FIRST_CAUTIOUS = [
    AtLeast(1, SPAWNINGPOOL),
    HATCHERY,
    EXTRACTOR,
    QUEEN,  # 1
    ZERGLING, ZERGLING,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    QUEEN,
    CanAfford(ZERGLINGMOVEMENTSPEED),
    CanAfford(SPINECRAWLER),
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    # If we don't yet have a lair but we have a baneling nest, build 7 cautionary banes
    IfHasThenDontBuild(LAIR, IfHasThenBuild(BANELINGNEST, BANELING, 7)),
    DRONE, DRONE, DRONE,
    IfHasThenDontBuild(LAIR, IfHasThenBuild(BANELINGNEST, ZERGLING, 8)),
    QUEEN,
]

# Enemy cheese found. Get a spawning pool first with Zerglings, Banelings, and Spine Crawlers
EARLY_GAME_POOL_FIRST_DEFENSIVE = [
    AtLeast(1, SPAWNINGPOOL),
    EXTRACTOR,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    QUEEN,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, CanAfford(BANELINGNEST)),
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, BANELING, 4),  # Build 4 banelings until we get a roach warren
    HATCHERY,
    QUEEN,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 4),  # Build 4 zerglings until we get a roach warren
    IfHasThenDontBuild(ROACHWARREN, BANELING, 4),  # Build 4 banelings until we get a roach warren
    QUEEN,
    DRONE,
    CanAfford(ZERGLINGMOVEMENTSPEED),
    DRONE, DRONE,
    IfHasThenDontBuild(ROACHWARREN, BANELING, 8),
    EXTRACTOR,
    QUEEN,
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 16),
]

# Get a spawning pool first with Zerglings for an all-in rush
EARLY_GAME_POOL_FIRST_OFFENSIVE = [
    EXTRACTOR,
    AtLeast(1, SPAWNINGPOOL),
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
    AtLeast(1, SPAWNINGPOOL),
    DRONE, DRONE,  # 21
    OVERLORD,  # 3
    QUEEN,  # 1
    ZERGLINGMOVEMENTSPEED,
    ZERGLING, ZERGLING,
    OneForEach(SPORECRAWLER, HATCHERY),  # One Spore Crawler for each Hatchery we own
    OneForEach(SPORECRAWLER, HATCHERY),  # Another Spore Crawler for each Hatchery we own
    SPORECRAWLER,  # One more because who needs drones anyways
    QUEEN,  # 2
    QUEEN,  # 3
    QUEEN,  # 4
]

# Early game pool first with 4 defensive Zerglings
EARLY_GAME_POOL_FIRST = [
    AtLeast(1, SPAWNINGPOOL),
    HATCHERY,  # 2 (First expand)
    EXTRACTOR,  # 1
    DRONE,  # 19
    QUEEN,  # 1
    ZERGLING, ZERGLING,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,  # 4
    QUEEN,  # 2
    CanAfford(ZERGLINGMOVEMENTSPEED),
    DRONE,
    DRONE,
]

# Get a hatchery first with 4 defensive Zerglings
EARLY_GAME_HATCHERY_FIRST = [
    HATCHERY,  # 2 (First expand)
    DRONE,  # 19
    EXTRACTOR,  # 1
    AtLeast(1, SPAWNINGPOOL),
    DRONE, DRONE, # 21
    OVERLORD,  # 3
    QUEEN,  # 1
    CanAfford(ZERGLINGMOVEMENTSPEED),
    ZERGLING, ZERGLING,
    QUEEN,  # 2
    ZERGLING, ZERGLING,  # 4
]

# Get a ling-bane mid-game composition
MID_GAME_LING_BANE = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    DRONE, DRONE,
    HATCHERY,
    AtLeast(3, QUEEN),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(2, EXTRACTOR),
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(1, BANELINGNEST),
    DRONE, DRONE,
    QUEEN,
    DRONE, DRONE,
    EVOLUTIONCHAMBER,
    CanAfford(LAIR),
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    CanAfford(ZERGMELEEWEAPONSLEVEL1),
    QUEEN,
    BANELING, BANELING,
    EXTRACTOR,
    EVOLUTIONCHAMBER,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,
    CanAfford(ZERGGROUNDARMORSLEVEL1),
    EXTRACTOR,
    UpgradeId.CENTRIFICALHOOKS,
    CanAfford(UpgradeId.OVERLORDSPEED),  # Baneling drops
]
MID_GAME_LING_BANE += ([ZERGLING] * 20 + [BANELING] * 10)
MID_GAME_LING_BANE += [
    CanAfford(BURROW),
    CanAfford(ZERGMELEEWEAPONSLEVEL2),
    CanAfford(ZERGGROUNDARMORSLEVEL2),
    INFESTATIONPIT,
    HATCHERY,
]
MID_GAME_LING_BANE += [
    UpgradeId.INFESTORENERGYUPGRADE,
]
MID_GAME_LING_BANE += ([ZERGLING] * 4 + [BANELING] * 2)
MID_GAME_LING_BANE += [
    INFESTOR, INFESTOR, INFESTOR,
]
MID_GAME_LING_BANE += ([ZERGLING] * 10 + [BANELING] * 4)
MID_GAME_LING_BANE += [
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    OVERSEER,
    QUEEN,
    QUEEN,
]


# Roach Hydra composition
MID_GAME_ROACH_HYDRA_LURKER = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    DRONE, DRONE,
    HATCHERY,
    DRONE, DRONE, DRONE,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    IfHasThenBuild(BANELINGNEST, ZERGLING, 10),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(3, EXTRACTOR),
    AtLeast(1, ROACHWARREN),
    DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,
    EXTRACTOR,
    EVOLUTIONCHAMBER,
    EVOLUTIONCHAMBER,
    IfHasThenDontBuild(GREATERSPIRE, ROACH, 5),  # Build 5 roaches until we get late-game tech
    RAVAGER, ROACH, ROACH, ROACH, RAVAGER, RAVAGER,
    CanAfford(ZERGMISSILEWEAPONSLEVEL1),
    CanAfford(ZERGGROUNDARMORSLEVEL1),
    CanAfford(LAIR),
    DRONE, DRONE, DRONE,
    RAVAGER,
    HATCHERY,
    QUEEN,
    IfHasThenBuild(BANELINGNEST, BANELING, 8),
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    DRONE, DRONE, DRONE, DRONE, DRONE,
    CanAfford(ZERGMISSILEWEAPONSLEVEL2),
    CanAfford(ZERGGROUNDARMORSLEVEL2),
    EXTRACTOR,
]
MID_GAME_ROACH_HYDRA_LURKER += [CanAfford(GLIALRECONSTITUTION)]
MID_GAME_ROACH_HYDRA_LURKER += [IfHasThenDontBuild(GREATERSPIRE, ROACH, 5)]  # Build extra roaches until late game
MID_GAME_ROACH_HYDRA_LURKER += [QUEEN] * 2
MID_GAME_ROACH_HYDRA_LURKER += [RAVAGER] * 2
MID_GAME_ROACH_HYDRA_LURKER += [EXTRACTOR] * 1
MID_GAME_ROACH_HYDRA_LURKER += [CanAfford(TUNNELINGCLAWS)]  # Roach burrow move
MID_GAME_ROACH_HYDRA_LURKER += [CanAfford(BURROW)]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISKDEN]
MID_GAME_ROACH_HYDRA_LURKER += [EXTRACTOR]
MID_GAME_ROACH_HYDRA_LURKER += [OVERSEER]
MID_GAME_ROACH_HYDRA_LURKER += [CanAfford(EVOLVEGROOVEDSPINES)]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 5
MID_GAME_ROACH_HYDRA_LURKER += [INFESTATIONPIT]
MID_GAME_ROACH_HYDRA_LURKER += [UpgradeId.INFESTORENERGYUPGRADE]
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 5
MID_GAME_ROACH_HYDRA_LURKER += [INFESTOR] * 3
MID_GAME_ROACH_HYDRA_LURKER += [OVERSEER, QUEEN] * 1
MID_GAME_ROACH_HYDRA_LURKER += [HYDRALISK] * 1
MID_GAME_ROACH_HYDRA_LURKER += [EVOLVEMUSCULARAUGMENTS]
MID_GAME_ROACH_HYDRA_LURKER += [HATCHERY]

# Tech up to Corruptor Brood Lord ASAP vs Tanks
# This is a midgame build we switch into against tanks
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH = [
    AtLeast(40, DRONE),
    AtLeast(2, EXTRACTOR),
    LAIR,
    IfHasThenBuild(BANELINGNEST, ZERGLING, 12),
    AtLeast(60, DRONE),
    IfHasThenBuild(BANELINGNEST, BANELING, 6),
    AtLeast(65, DRONE),
    AtLeast(1, INFESTATIONPIT),
    AtLeast(5, HATCHERY),
    AtLeast(8, EXTRACTOR),
    IfHasThenDontBuild(GREATERSPIRE, SPIRE),
    HIVE,
    AtLeast(70, DRONE),
    IfHasThenBuild(ROACHWARREN, ROACH, 3),
    IfHasThenBuild(BANELINGNEST, ZERGLING, 12),
    IfHasThenBuild(BANELINGNEST, BANELING, 6),
    IfHasThenBuild(HYDRALISKDEN, HYDRALISK, 10),
    IfHasThenBuild(ROACHWARREN, RAVAGER, 3),
]
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [CORRUPTOR] * 5
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [GREATERSPIRE]
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [AtLeast(16, OVERLORD)]
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [CORRUPTOR] * 2
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [ZERGFLYERWEAPONSLEVEL1]
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [BROODLORD] * 15
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [ZERGFLYERWEAPONSLEVEL2]
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH += [ZERGFLYERARMORSLEVEL1]


MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING = [
    # Publish a message saying we shouldn't switch to MOVING_TO_ATTACK or ATTACK
    # We want to attack through the nydus worm
    PublishMessage(Messages.DONT_ATTACK),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(4, QUEEN),
    DRONE, DRONE, DRONE, DRONE,
    AtLeast(2, EXTRACTOR),
    LAIR,
    AtLeast(4, EXTRACTOR),
    AtLeast(1, SPINECRAWLER),
    ROACHWARREN,
    DRONE, DRONE, DRONE,
    NYDUSNETWORK,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE,

    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    OVERSEER, OVERSEER,
    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    QUEEN,
    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    QUEEN,
]

LATE_GAME_CORRUPTOR_BROOD_LORD = [
    AtLeast(75, DRONE),
    AtLeast(1, INFESTATIONPIT),
    # If we have a hydralisk den, build additional hydras until we have a greater spire
    # Require at least one spire unless we have a Greater Spire
    AtLeast(1, HIVE),
    IfHasThenBuild(HYDRALISKDEN, IfHasThenDontBuild(GREATERSPIRE, HYDRALISK, 4)),
    AtLeast(6, HATCHERY),
    AtLeast(8, EXTRACTOR),
    # Get late game upgrades
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGLINGATTACKSPEED),
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGGROUNDARMORSLEVEL2, ZERGGROUNDARMORSLEVEL3),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGMELEEWEAPONSLEVEL3),
    IfHasThenDontBuild(GREATERSPIRE, AtLeast(1, SPIRE)),
    GREATERSPIRE,
    AtLeast(6, CORRUPTOR),
    OVERSEER,
]
LATE_GAME_CORRUPTOR_BROOD_LORD += [BROODLORD] * 20
LATE_GAME_CORRUPTOR_BROOD_LORD += [
    AtLeast(1, ZERGFLYERWEAPONSLEVEL1),
    AtLeast(1, ZERGFLYERWEAPONSLEVEL2)]


LATE_GAME_ULTRALISK = [
    AtLeast(75, DRONE),
    AtLeast(1, INFESTATIONPIT),
    AtLeast(1, HIVE),
    AtLeast(6, HATCHERY),
    AtLeast(8, EXTRACTOR),
    # Get late game upgrades
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGLINGATTACKSPEED),
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGGROUNDARMORSLEVEL2, ZERGGROUNDARMORSLEVEL3),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGMELEEWEAPONSLEVEL3),
    ULTRALISKCAVERN,
    ULTRALISK, ULTRALISK, ULTRALISK,
    UpgradeId.CHITINOUSPLATING,
    ULTRALISK, ULTRALISK, ULTRALISK, ULTRALISK, ULTRALISK,
    UpgradeId.ANABOLICSYNTHESIS,
]
LATE_GAME_ULTRALISK += [ULTRALISK] * 30


class Builds(enum.Enum):
    """Build Types"""

    EARLY_GAME_DEFAULT_OPENER = 0
    RAVAGER_ALL_IN = 1
    OPENER_RAVAGER_HARASS = 2

    EARLY_GAME_POOL_FIRST_CAUTIOUS = 3
    EARLY_GAME_POOL_FIRST_DEFENSIVE = 4
    EARLY_GAME_POOL_FIRST_OFFENSIVE = 5
    EARLY_GAME_POOL_FIRST = 6
    EARLY_GAME_HATCHERY_FIRST = 7
    EARLY_GAME_SPORE_CRAWLERS = 8

    MID_GAME_LING_BANE = 9
    MID_GAME_ROACH_HYDRA_LURKER = 10
    MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING = 11
    MID_GAME_CORRUPTOR_BROOD_LORD_RUSH = 12

    LATE_GAME_CORRUPTOR_BROOD_LORD = 13
    LATE_GAME_ULTRALISK = 14


class BuildStages(enum.Enum):
    """Stages of the game"""
    OPENING = 0
    EARLY_GAME = 1
    MID_GAME = 2
    LATE_GAME = 3


OPENER_BUILDS = {
    Builds.EARLY_GAME_DEFAULT_OPENER,
    Builds.RAVAGER_ALL_IN,
    Builds.OPENER_RAVAGER_HARASS,
}

EARLY_GAME_BUILDS = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_SPORE_CRAWLERS,
}

MID_GAME_BUILDS = {
    Builds.MID_GAME_LING_BANE,
    Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING,
    Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH,
}

LATE_GAME_BUILDS = {
    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.LATE_GAME_ULTRALISK,
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
    Builds.RAVAGER_ALL_IN: RAVAGER_ALL_IN,
    Builds.OPENER_RAVAGER_HARASS: OPENER_RAVAGER_HARASS,

    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_SPORE_CRAWLERS: EARLY_GAME_SPORE_CRAWLERS,
    Builds.EARLY_GAME_POOL_FIRST: EARLY_GAME_POOL_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST: EARLY_GAME_HATCHERY_FIRST,

    Builds.MID_GAME_LING_BANE: MID_GAME_LING_BANE,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING: MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING,
    Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH: MID_GAME_CORRUPTOR_BROOD_LORD_RUSH,

    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.LATE_GAME_ULTRALISK: LATE_GAME_ULTRALISK,
}

# Mapping of build to default next build
# The default build is switched to if the build is at its end
DEFAULT_NEXT_BUILDS = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_POOL_FIRST,
    Builds.RAVAGER_ALL_IN: None,
    Builds.OPENER_RAVAGER_HARASS: Builds.EARLY_GAME_DEFAULT_OPENER,

    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,

    Builds.MID_GAME_LING_BANE: Builds.LATE_GAME_ULTRALISK,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,

    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: None,
    Builds.LATE_GAME_ULTRALISK: None,
}

# Changes to default build if enemy is terran
DEFAULT_NEXT_BUILDS_TERRAN = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
}
DEFAULT_NEXT_BUILDS_ZERG = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.MID_GAME_LING_BANE,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_LING_BANE,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_LING_BANE,
}
DEFAULT_NEXT_BUILDS_PROTOSS = {
    Builds.EARLY_GAME_DEFAULT_OPENER: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
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


# Set of builds that must set their default next build after they are completed
# This is for builds that we don't want to keep around in the build order when we're through with them.
FORCE_DEFAULT_NEXT_BUILDS = {
    Builds.OPENER_RAVAGER_HARASS
}
