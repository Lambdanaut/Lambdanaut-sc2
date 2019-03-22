"""
Build Orders
============

* Opener build orders should always end with 17 drones if they intend to transition into another build
"""

from typing import Callable
import uuid

import lib.sc2 as sc2
from lib.sc2.constants import *

from lambdanaut.const2 import BuildManagerFlags, Messages


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

    NOTE: This ENDS when a build stage ends. Workers will be put back to full
    gas saturation at the end of a build stage.

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

    Example that will publish a message to send the second overlord to the
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


class IfFlagIsSet(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that if the const2.BuildManagerFlags `flag` is set,
    then we can build one or more of `unit_type`

    Example that will research Neural Parasite if the flag
    `ALLOW_NEURAL_PARASITE_UPGRADE` has been set.

        BUILD = [
            IfFlagIsSet(BuildManagerFlags.ALLOW_NEURAL_PARASITE_UPGRADE,
                        UpgradeId.NEURALPARASITE),
        ]
    """
    def __init__(self, flag: BuildManagerFlags, unit_type, n=1):
        super(IfFlagIsSet, self).__init__()

        self.unit_type = unit_type
        self.flag = flag
        self.n = n


class RunFunction(SpecialBuildTarget):
    """
    Container object for use in builds

    Functionally it means that we run `func` the first time this is hit in
    a build order.

    NOTE: Cannot be wrapped recursively.
    This is not valid: `RunFunction(AtLeast(1, ZERGLING))`

    Example that will run a function that returns `true` and stores it in
    the `self.result` variable.

        BUILD = [
            RunFunction(lambda bot: True),
        ]
    """
    def __init__(self, func):
        super(RunFunction, self).__init__()

        self.unit_type = None
        self.function: Callable[[sc2.BotAI], bool] = func
        self.result = None  # Hold the result of `self.function()`


# #################################### OPENERS #####################################

# A good basic macro opener. Always start here
OPENER_DEFAULT = [
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    DRONE,  # 13
    OVERLORD,  # 2
    DRONE,  # 14
    DRONE,  # 15
    DRONE,  # 16
    DRONE,  # 17
]


# 12 Pool opener for defense or early aggression
OPENER_12_POOL = [
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    SPAWNINGPOOL,  # 1
    DRONE,  # 13
    OVERLORD,  # 2
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    DRONE,  # 14
    DRONE,  # 15
    DRONE,  # 16
    DRONE,  # 17
    OVERLORD,  # 3
]


# A ZvZ spine rush
# This build works like shit and it should never be used
def early_game_pool_spine_all_in_send_workers_to_enemy(bot: sc2.BotAI) -> bool:
    """
    Function that sends workers to enemy base in preparation for building spine crawlers
    """

    # Get workers within range of a townhall
    workers = bot.workers.filter(lambda w: bot.townhalls.closer_than(15, w))

    if workers:
        workers = workers.take(len(workers) - 3)
        if workers:
            for worker in workers:
                bot.actions.append(worker.attack(bot.enemy_start_location))
            return True
    return False


EARLY_GAME_POOL_SPINE_ALL_IN = [
    # Publish message to indicate we should build spines in opponents base
    PublishMessage(Messages.BUILD_OFFENSIVE_SPINES),
    PublishMessage(Messages.DONT_RETURN_DISTANT_WORKERS_TO_TOWNHALLS),
    HATCHERY,  # 1
    OVERLORD,  # 1
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,  # 12
    SPAWNINGPOOL,
    DRONE,  # 13
    DRONE,  # 14
    OVERLORD,  # 2
    ZERGLING, ZERGLING,  # 2
    ZERGLING, ZERGLING,  # 4
    ZERGLING, ZERGLING,  # 6
    ZERGLING, ZERGLING,  # 8
    RunFunction(early_game_pool_spine_all_in_send_workers_to_enemy),
    SPINECRAWLER, SPINECRAWLER, SPINECRAWLER,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    OVERLORD,  # 3
]
EARLY_GAME_POOL_SPINE_ALL_IN += [ZERGLING] * 400


# Ravager all-in with no transition
RAVAGER_ALL_IN = [
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
    EXTRACTOR,  # 2
    OVERLORD,  # 3
    ROACHWARREN,
    OVERLORD,  # 4  (Extra in case we lose one)
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
    DRONE,  # 15
    ROACHWARREN,
    ROACH,
    IfHasThenDontBuild(RAVAGER, ROACH, 3),
    RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    # Pull workers off vespene for 60 seconds
    QUEEN,
    DRONE,  # 16
    PublishMessage(Messages.PULL_WORKERS_OFF_VESPENE_FOR_X_SECONDS, 60),
    DRONE,  # 17
]


# #################################### EARLY GAME #####################################


# Suspect enemy cheese but no proof. Get a spawning pool first with Zerglings
EARLY_GAME_POOL_FIRST_CAUTIOUS = [
    AtLeast(1, SPAWNINGPOOL),
    HATCHERY,
    EXTRACTOR,
    QUEEN,  # 1
    ZERGLING, ZERGLING,
    OVERLORD,  # 3
    ZERGLING, ZERGLING,
    CanAfford(SPINECRAWLER),
    CanAfford(ZERGLINGMOVEMENTSPEED),
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    QUEEN,  # 2
    IfHasThenBuild(BANELINGNEST, BANELING, 6),  # Build 6 banelings if we have a baneling nest
    DRONE, DRONE, DRONE, DRONE,
]


# Enemy cheese found. Get a spawning pool first with Zerglings, Banelings, and Spine Crawlers
EARLY_GAME_POOL_FIRST_DEFENSIVE = [
    # Return workers to vespene gas
    PublishMessage(Messages.CLEAR_PULLING_WORKERS_OFF_VESPENE),

    AtLeast(1, SPAWNINGPOOL),
    EXTRACTOR,
    AtLeast(3, OVERLORD),  # 3
    IfHasThenDontBuild(BANELINGNEST, ZERGLING, 2),  # Focus on getting banelings out at this point
    QUEEN,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(BANELINGNEST, ZERGLING, 2),
    IfHasThenDontBuild(ROACHWARREN, BANELINGNEST),
    ZERGLING, ZERGLING,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, BANELING, 4),  # Build 4 banelings until we get a roach warren
    ZERGLING, ZERGLING,
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 6),  # Build 4 zerglings until we get a roach warren
    DRONE, DRONE,
    EXTRACTOR,
    DRONE, DRONE,
    CanAfford(ZERGLINGMOVEMENTSPEED),
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, BANELING, 2),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 8),
    HATCHERY,
    QUEEN,
    IfHasThenDontBuild(ROACHWARREN, BANELING, 4),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 24),
    IfHasThenDontBuild(ROACHWARREN, BANELING, 2),
]


# Get a spawning pool first with Zerglings for early aggression
EARLY_GAME_POOL_FIRST_OFFENSIVE = [
    EXTRACTOR,
    AtLeast(1, SPAWNINGPOOL),
    AtLeast(3, OVERLORD),  # 3
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    QUEEN,  # 1
    ZERGLINGMOVEMENTSPEED,
    HATCHERY,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    QUEEN,  # 2
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
    ZERGLING, ZERGLING,
]


# Enemy cheese found. Get a spawning pool and roach warren with ravagers. Good Vs proxy hatch spines
EARLY_GAME_ROACH_RAVAGER_DEFENSIVE = [
    AtLeast(1, SPAWNINGPOOL),
    AtLeast(3, OVERLORD),  # 3
    ZERGLING, ZERGLING,
    QUEEN,
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 2),
    CanAfford(SPINECRAWLER),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, 2),
    EXTRACTOR,
    DRONE, DRONE, DRONE,  # 21
    EXTRACTOR,
    ROACHWARREN,
    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    QUEEN,
    RAVAGER,
    HATCHERY,
    RAVAGER, RAVAGER,
    DRONE,
    ZERGLINGMOVEMENTSPEED,
]


# Get a Hatchery first with Zerglings for an all-in rush
# This build punishes greedy opponents we've scouted
EARLY_GAME_HATCHERY_FIRST_LING_RUSH = [
    HATCHERY,  # 2 (First expand)
    EXTRACTOR,  # 1
    AtLeast(1, SPAWNINGPOOL),
    DRONE,  # 18
    DRONE, DRONE,  # 20
    AtLeast(3, OVERLORD),  # 3
    QUEEN,  # 1
    ZERGLINGMOVEMENTSPEED,
    # Keep workers on vespene gas
    PublishMessage(Messages.CLEAR_PULLING_WORKERS_OFF_VESPENE),
    ZERGLING, ZERGLING,
    QUEEN,  # 2
    ZERGLING, ZERGLING,  # 4
    DRONE,  # 21
    BANELINGNEST,
]
EARLY_GAME_HATCHERY_FIRST_LING_RUSH += [ZERGLING] * 20
EARLY_GAME_HATCHERY_FIRST_LING_RUSH += [BANELING] * 10
EARLY_GAME_HATCHERY_FIRST_LING_RUSH += [ZERGLING] * 5
EARLY_GAME_HATCHERY_FIRST_LING_RUSH += [BANELING] * 2
EARLY_GAME_HATCHERY_FIRST_LING_RUSH += [ZERGLING] * 25


# Seen enemy air units / air tech (Banshees, Mutas, Liberators, Oracle...)
EARLY_GAME_SPORE_CRAWLERS = [
    DRONE,  # 18
    EXTRACTOR,  # 1
    AtLeast(1, SPAWNINGPOOL),
    DRONE, DRONE, DRONE,  # 21
    AtLeast(3, OVERLORD),  # 3
    QUEEN,  # 1
    ZERGLINGMOVEMENTSPEED,
    ZERGLING, ZERGLING,
    # One Spore Crawler for each Hatchery we own
    OneForEach(SPORECRAWLER, HATCHERY),
    IfHasThenDontBuild(ROACHWARREN, ZERGLING, ),
    # One more Spore Crawler for each Hatchery we own if we're defending aggressively. Also two extra.
    IfFlagIsSet(BuildManagerFlags.AGGRESSIVE_AIR_DEFENSE, OneForEach(SPORECRAWLER, HATCHERY)),
    IfFlagIsSet(BuildManagerFlags.AGGRESSIVE_AIR_DEFENSE, SPORECRAWLER, n=2),
    HATCHERY,  # 2 (First expand)
    QUEEN,  # 2
]


# Early game pool first with 4 defensive Zerglings
EARLY_GAME_POOL_FIRST = [
    AtLeast(1, SPAWNINGPOOL),
    HATCHERY,  # 2 (First expand)
    EXTRACTOR,  # 1
    DRONE,  # 18
    QUEEN,  # 1
    ZERGLING, ZERGLING,
    AtLeast(3, OVERLORD),  # 3
    ZERGLING, ZERGLING,  # 4
    QUEEN,  # 2
    CanAfford(ZERGLINGMOVEMENTSPEED),
    DRONE, DRONE, DRONE,  # 21
]


# Get a hatchery first with 4 defensive Zerglings
EARLY_GAME_HATCHERY_FIRST = [
    HATCHERY,  # 2 (First expand)
    EXTRACTOR,  # 1
    AtLeast(1, SPAWNINGPOOL),
    DRONE,  # 18
    DRONE, DRONE,  # 20
    AtLeast(3, OVERLORD),  # 3
    QUEEN,  # 1
    CanAfford(ZERGLINGMOVEMENTSPEED),
    ZERGLING, ZERGLING,
    QUEEN,  # 2
    ZERGLING, ZERGLING,  # 4
    DRONE,  # 21
]


# Get a hatchery first with 4 defensive Zerglings. Go for another hatchery soon after.
EARLY_GAME_HATCHERY_FIRST_GREEDY = [
    HATCHERY,  # 2 (First expand)
    DRONE,  # 18
    EXTRACTOR,  # 1
    AtLeast(1, SPAWNINGPOOL),
    DRONE, DRONE,  # 20
    AtLeast(3, OVERLORD),  # 3
    CanAfford(ZERGLINGMOVEMENTSPEED),
    ZERGLING, ZERGLING,
    HATCHERY,  # 3  (Greedy third hatchery)
    QUEEN,  # 1
    QUEEN,  # 2
    DRONE,  # 21
    ZERGLING, ZERGLING,
]  # 27 Supply


# #################################### MID GAME #####################################


# Get a ling-bane mid-game composition
MID_GAME_LING_BANE_HYDRA = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    AtLeast(3, HATCHERY),
    DRONE,
    DRONE,
    ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE,
    ZERGLING, ZERGLING,
    AtLeast(3, QUEEN),
    ZERGLING, ZERGLING,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(2, EXTRACTOR),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(1, BANELINGNEST),
    ZERGLING, ZERGLING, ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    CanAfford(LAIR),
]
MID_GAME_LING_BANE_HYDRA += ([ZERGLING] * 22)
MID_GAME_LING_BANE_HYDRA += ([BANELING] * 8)
MID_GAME_LING_BANE_HYDRA += [
    EVOLUTIONCHAMBER, EVOLUTIONCHAMBER,
    CanAfford(ZERGMELEEWEAPONSLEVEL1),
    QUEEN,
    CanAfford(ZERGGROUNDARMORSLEVEL1),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    EXTRACTOR,  # 3
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    OVERSEER,
    HYDRALISKDEN,
    HATCHERY,
    EXTRACTOR, EXTRACTOR,  # 5
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    HATCHERY,
    EXTRACTOR,  # 6
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    UpgradeId.CENTRIFICALHOOKS,
    UpgradeId.EVOLVEMUSCULARAUGMENTS,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    LURKERDENMP,  # Lurkers
    # CanAfford(UpgradeId.OVERLORDSPEED),  # Baneling drops
    EXTRACTOR,  # 7
    CanAfford(ZERGMISSILEWEAPONSLEVEL1),
    CanAfford(ZERGGROUNDARMORSLEVEL2),
]
MID_GAME_LING_BANE_HYDRA += [
    EXTRACTOR,  # 8
    INFESTATIONPIT,
    UpgradeId.INFESTORENERGYUPGRADE,
    EVOLVEGROOVEDSPINES,
    IfHasThenDontBuild(ULTRALISKCAVERN, HYDRALISK, 5),
    LURKERMP, LURKERMP, LURKERMP, LURKERMP, LURKERMP,
    BURROW,  # Burrow banelings and infestors
]
MID_GAME_LING_BANE_HYDRA += [
    INFESTOR, INFESTOR, INFESTOR,
    IfFlagIsSet(BuildManagerFlags.ALLOW_NEURAL_PARASITE_UPGRADE, UpgradeId.NEURALPARASITE),
    LURKERMP, LURKERMP,
    OVERSEER,
]
MID_GAME_LING_BANE_HYDRA += [
    QUEEN,
    ZERGMISSILEWEAPONSLEVEL2,
    ZERGMELEEWEAPONSLEVEL2,
    IfHasThenDontBuild(ULTRALISKCAVERN, HYDRALISK, 6),
]


# Roach Hydra composition
MID_GAME_ROACH_HYDRA_LURKER = [
    AtLeast(1, ZERGLINGMOVEMENTSPEED),
    AtLeast(3, HATCHERY),
    DRONE,
    DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    IfHasThenBuild(BANELINGNEST, ZERGLING, 4),
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(1, ROACHWARREN),
    DRONE, DRONE, DRONE, DRONE,
    AtLeast(3, EXTRACTOR),
    IfHasThenDontBuild(HYDRALISKDEN, ROACH, 5),  # Build 5 roaches until hydralisk den arrives
    EXTRACTOR,
    ROACH, ROACH, ROACH,
    RAVAGER, RAVAGER, RAVAGER,
    EVOLUTIONCHAMBER,
    RAVAGER,
    CanAfford(ZERGMISSILEWEAPONSLEVEL1),
    EXTRACTOR,
    EVOLUTIONCHAMBER,
    IfHasThenDontBuild(HYDRALISKDEN, ROACH, 2),  # Build extra roaches until hydralisk den arrives
    CanAfford(ZERGGROUNDARMORSLEVEL1),
    CanAfford(LAIR),
    IfHasThenDontBuild(GREATERSPIRE, ROACH, 8),  # Build extra roaches until late game
    RAVAGER, RAVAGER,
    QUEEN,
    EXTRACTOR,
    IfHasThenBuild(BANELINGNEST, BANELING, 6),
    HATCHERY,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    CanAfford(GLIALRECONSTITUTION),
    DRONE, DRONE, DRONE,
    QUEEN,
    HYDRALISKDEN,
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    QUEEN,
    CanAfford(BURROW),
    CanAfford(TUNNELINGCLAWS),  # Roach burrow move
    IfHasThenDontBuild(LURKERDENMP, HYDRALISK, 3),
    EXTRACTOR,
    HATCHERY,
    OVERSEER,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    EXTRACTOR,
    CanAfford(ZERGMISSILEWEAPONSLEVEL2),
    CanAfford(ZERGGROUNDARMORSLEVEL2),
    EVOLVEGROOVEDSPINES,
    INFESTATIONPIT,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    UpgradeId.INFESTORENERGYUPGRADE,
    HYDRALISK, HYDRALISK,
    INFESTOR, INFESTOR, INFESTOR,
    IfFlagIsSet(BuildManagerFlags.ALLOW_NEURAL_PARASITE_UPGRADE, UpgradeId.NEURALPARASITE),
    LURKERDENMP,
    OVERSEER,
    EVOLVEMUSCULARAUGMENTS,
    LURKERMP, LURKERMP, LURKERMP, LURKERMP,
]


# Tech up to Corruptor Brood Lord ASAP vs Tanks
# This is a midgame build we switch into against tanks
MID_GAME_CORRUPTOR_BROOD_LORD_RUSH = [
    AtLeast(3, HATCHERY),
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


# Tech to lair and nydus for a timing attack through nydus worm
MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING = [
    # Publish a message saying we shouldn't switch to MOVING_TO_ATTACK or ATTACK
    # We want to attack through the nydus worm

    # PublishMessage(Messages.ALLOW_ATTACKING_THROUGH_NYDUS),
    # PublishMessage(Messages.DONT_ATTACK),

    DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(3, QUEEN),
    DRONE, DRONE, DRONE, DRONE,
    AtLeast(2, EXTRACTOR),
    LAIR,
    AtLeast(4, EXTRACTOR),
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(1, SPINECRAWLER),
    QUEEN,
    ROACHWARREN,
    NYDUSNETWORK,
    QUEEN,

    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    OVERSEER, OVERSEER,
    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER, RAVAGER,
    QUEEN,
    ROACH, ROACH, ROACH, ROACH, ROACH, ROACH, ROACH,
    QUEEN,
]

# Tech to lair and hydralisk for a timing attack against air superiority
MID_GAME_TWO_BASE_HYDRA_TIMING = [
    # Put workers on vespene gas. Gas heavy work coming
    PublishMessage(Messages.CLEAR_PULLING_WORKERS_OFF_VESPENE),
    ZERGLING, ZERGLING, ZERGLING, ZERGLING,
    AtLeast(3, QUEEN),
    DRONE, DRONE, DRONE, DRONE, DRONE,
    AtLeast(2, EXTRACTOR),
    DRONE, DRONE, DRONE, DRONE,
    LAIR,
    AtLeast(4, EXTRACTOR),
    DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE, DRONE,
    HYDRALISKDEN,
    QUEEN,
    OVERSEER, OVERSEER,
    HYDRALISK, HYDRALISK, HYDRALISK,
    UpgradeId.EVOLVEGROOVEDSPINES,
    HYDRALISK, HYDRALISK,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
    UpgradeId.EVOLVEMUSCULARAUGMENTS,
    HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK, HYDRALISK,
]


# #################################### LATE GAME #####################################


LATE_GAME_CORRUPTOR_BROOD_LORD = [
    AtLeast(75, DRONE),
    AtLeast(1, INFESTATIONPIT),
    # If we have a hydralisk den, build additional hydras until we have a greater spire
    # Require at least one spire unless we have a Greater Spire
    AtLeast(1, HIVE),
    IfHasThenDontBuild(GREATERSPIRE, IfHasThenBuild(HYDRALISKDEN, HYDRALISK, 6)),
    AtLeast(6, HATCHERY),
    AtLeast(9, EXTRACTOR),
    # Get late game upgrades
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGLINGATTACKSPEED),
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGGROUNDARMORSLEVEL2, ZERGGROUNDARMORSLEVEL3),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGMELEEWEAPONSLEVEL3),
    IfHasThenBuild(LURKERDENMP, UpgradeId.DIGGINGCLAWS),  # Lurker Adaptive Talons
    IfHasThenDontBuild(GREATERSPIRE, AtLeast(1, SPIRE)),
    GREATERSPIRE,
    CORRUPTOR, CORRUPTOR, CORRUPTOR,
    IfHasThenDontBuild(BROODLORD, CORRUPTOR, 5),
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
    AtLeast(9, EXTRACTOR),
    # Get late game upgrades
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGLINGATTACKSPEED),
    IfHasThenBuild(ZERGMISSILEWEAPONSLEVEL2, ZERGMISSILEWEAPONSLEVEL3),
    IfHasThenBuild(ZERGGROUNDARMORSLEVEL2, ZERGGROUNDARMORSLEVEL3),
    IfHasThenBuild(ZERGMELEEWEAPONSLEVEL2, ZERGMELEEWEAPONSLEVEL3),
    IfHasThenBuild(LURKERDENMP, UpgradeId.DIGGINGCLAWS),  # Lurker Adaptive Talons
    ULTRALISKCAVERN,
    ULTRALISK, ULTRALISK, ULTRALISK,
    UpgradeId.CHITINOUSPLATING,
    ULTRALISK, ULTRALISK, ULTRALISK, ULTRALISK,
    UpgradeId.ANABOLICSYNTHESIS,
]
LATE_GAME_ULTRALISK += [ULTRALISK] * 30


class Builds(enum.Enum):
    """Build Types"""

    OPENER_DEFAULT = 0
    OPENER_12_POOL = 1
    EARLY_GAME_POOL_SPINE_ALL_IN = 2
    RAVAGER_ALL_IN = 3
    OPENER_RAVAGER_HARASS = 4

    EARLY_GAME_POOL_FIRST_CAUTIOUS = 5
    EARLY_GAME_POOL_FIRST_DEFENSIVE = 6
    EARLY_GAME_ROACH_RAVAGER_DEFENSIVE = 7
    EARLY_GAME_POOL_FIRST_OFFENSIVE = 8
    EARLY_GAME_HATCHERY_FIRST_LING_RUSH = 9
    EARLY_GAME_POOL_FIRST = 10
    EARLY_GAME_HATCHERY_FIRST = 11
    EARLY_GAME_HATCHERY_FIRST_GREEDY = 12
    EARLY_GAME_SPORE_CRAWLERS = 13

    MID_GAME_LING_BANE_HYDRA = 14
    MID_GAME_ROACH_HYDRA_LURKER = 15
    MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING = 16
    MID_GAME_TWO_BASE_HYDRA_TIMING = 17
    MID_GAME_CORRUPTOR_BROOD_LORD_RUSH = 18

    LATE_GAME_CORRUPTOR_BROOD_LORD = 19
    LATE_GAME_ULTRALISK = 20


class BuildStages(enum.Enum):
    """Stages of the game"""
    OPENING = 0
    EARLY_GAME = 1
    MID_GAME = 2
    LATE_GAME = 3


OPENER_BUILDS = {
    Builds.OPENER_DEFAULT,
    Builds.OPENER_12_POOL,
    Builds.EARLY_GAME_POOL_SPINE_ALL_IN,
    Builds.RAVAGER_ALL_IN,
    Builds.OPENER_RAVAGER_HARASS,
}

EARLY_GAME_BUILDS = {
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH,
    Builds.EARLY_GAME_POOL_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY,
    Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_SPORE_CRAWLERS,
}

MID_GAME_BUILDS = {
    Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING,
    Builds.MID_GAME_TWO_BASE_HYDRA_TIMING,
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
    Builds.OPENER_DEFAULT: OPENER_DEFAULT,
    Builds.OPENER_12_POOL: OPENER_12_POOL,
    Builds.EARLY_GAME_POOL_SPINE_ALL_IN: EARLY_GAME_POOL_SPINE_ALL_IN,
    Builds.RAVAGER_ALL_IN: RAVAGER_ALL_IN,
    Builds.OPENER_RAVAGER_HARASS: OPENER_RAVAGER_HARASS,

    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE: EARLY_GAME_ROACH_RAVAGER_DEFENSIVE,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: EARLY_GAME_POOL_FIRST_OFFENSIVE,
    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH: EARLY_GAME_HATCHERY_FIRST_LING_RUSH,
    Builds.EARLY_GAME_SPORE_CRAWLERS: EARLY_GAME_SPORE_CRAWLERS,
    Builds.EARLY_GAME_POOL_FIRST: EARLY_GAME_POOL_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST: EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY: EARLY_GAME_HATCHERY_FIRST_GREEDY,

    Builds.MID_GAME_LING_BANE_HYDRA: MID_GAME_LING_BANE_HYDRA,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING: MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING,
    Builds.MID_GAME_TWO_BASE_HYDRA_TIMING: MID_GAME_TWO_BASE_HYDRA_TIMING,
    Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH: MID_GAME_CORRUPTOR_BROOD_LORD_RUSH,

    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.LATE_GAME_ULTRALISK: LATE_GAME_ULTRALISK,
}

# Mapping of build to default next build
# The default build is switched to if the build is at its end
DEFAULT_NEXT_BUILDS = {
    Builds.OPENER_DEFAULT: Builds.EARLY_GAME_POOL_FIRST,
    Builds.OPENER_12_POOL: Builds.OPENER_DEFAULT,
    Builds.EARLY_GAME_POOL_SPINE_ALL_IN: None,
    Builds.RAVAGER_ALL_IN: None,
    Builds.OPENER_RAVAGER_HARASS: Builds.OPENER_DEFAULT,

    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_OFFENSIVE: Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS,
    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY: Builds.MID_GAME_ROACH_HYDRA_LURKER,

    Builds.MID_GAME_LING_BANE_HYDRA: Builds.LATE_GAME_ULTRALISK,
    Builds.MID_GAME_ROACH_HYDRA_LURKER: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_TWO_BASE_HYDRA_TIMING: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.MID_GAME_CORRUPTOR_BROOD_LORD_RUSH: Builds.LATE_GAME_CORRUPTOR_BROOD_LORD,

    Builds.LATE_GAME_CORRUPTOR_BROOD_LORD: None,
    Builds.LATE_GAME_ULTRALISK: None,
}

# Changes to default build if enemy is terran
DEFAULT_NEXT_BUILDS_TERRAN = {
    Builds.OPENER_DEFAULT: Builds.EARLY_GAME_HATCHERY_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_LING_BANE_HYDRA,
}
DEFAULT_NEXT_BUILDS_ZERG = {
    Builds.OPENER_DEFAULT: Builds.EARLY_GAME_POOL_FIRST,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_POOL_FIRST: Builds.MID_GAME_LING_BANE_HYDRA,
    Builds.EARLY_GAME_SPORE_CRAWLERS: Builds.MID_GAME_LING_BANE_HYDRA,
}
DEFAULT_NEXT_BUILDS_PROTOSS = {
    Builds.OPENER_DEFAULT: Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY,
    Builds.EARLY_GAME_POOL_FIRST_CAUTIOUS: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST: Builds.MID_GAME_ROACH_HYDRA_LURKER,
    Builds.EARLY_GAME_HATCHERY_FIRST_GREEDY: Builds.MID_GAME_ROACH_HYDRA_LURKER,
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
# The next default build MUST be in the same build stage as the build in this set.
FORCE_DEFAULT_NEXT_BUILDS = {
    Builds.OPENER_RAVAGER_HARASS,
    Builds.OPENER_12_POOL,
    Builds.EARLY_GAME_POOL_FIRST_DEFENSIVE,
    Builds.EARLY_GAME_ROACH_RAVAGER_DEFENSIVE,
    Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH,
    Builds.MID_GAME_TWO_BASE_HYDRA_TIMING,
    Builds.MID_GAME_TWO_BASE_ROACH_QUEEN_NYDUS_TIMING,
}
