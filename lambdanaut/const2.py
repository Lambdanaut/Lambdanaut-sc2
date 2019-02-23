"""
Class to add further constants from data_pb2
"""

import enum

import lib.sc2 as sc2
import lib.sc2.constants as const
from s2clientprotocol import data_pb2

# About number of frames per second on faster speed
FPS = 22

# Set of zerg structures built from drones
ZERG_STRUCTURES_FROM_DRONES = \
    {const.HATCHERY, const.SPAWNINGPOOL, const.EXTRACTOR, const.EVOLUTIONCHAMBER, const.SPORECRAWLER,
     const.BANELINGNEST, const.ROACHWARREN, const.SPINECRAWLER, const.SPIRE, const.NYDUSNETWORK,
     const.INFESTATIONPIT, const.HYDRALISKDEN, const.LURKERDENMP, const.ULTRALISKCAVERN, }

ZERG_UNITS_FROM_LARVAE = \
    {const.DRONE, const.OVERLORD, const.ZERGLING, const.ROACH, const.HYDRALISK, const.INFESTOR,
     const.UnitTypeId.SWARMHOSTMP, const.MUTALISK, const.CORRUPTOR, const.ULTRALISK, const.VIPER, }

ZERG_UNITS_FROM_STRUCTURES = {const.QUEEN}

ZERG_ARMY_UNITS = \
    {const.ZERGLING, const.BANELING, const.ROACH, const.RAVAGER, const.HYDRALISK, const.MUTALISK, const.OVERSEER,
     const.INFESTOR, const.CORRUPTOR, const.VIPER, const.BROODLORD, const.ULTRALISK, }

# All zerg units including structures (Excludes special forms like DRONEBURROWED)
ZERG_UNITS = \
    {const.HYDRALISK, const.NYDUSCANAL, const.LURKERDENMP, const.NYDUSNETWORK, const.VIPER, const.RAVAGER,
     const.SPAWNINGPOOL, const.DRONE, const.OVERLORD, const.CORRUPTOR, const.HATCHERY, const.MUTALISK, const.LAIR,
     const.NYDUSCANALCREEPER, const.INFESTOR, const.LURKERMP, const.OVERSEER, const.EXTRACTOR,
     const.EVOLUTIONCHAMBER, const.QUEEN, const.BROODLORD, const.ROACHWARREN, const.NYDUSCANALATTACKER,
     const.ULTRALISKCAVERN, const.BANELING, const.SPORECRAWLER, const.BANELINGNEST, const.GREATERSPIRE, const.HIVE,
     const.INFESTATIONPIT, const.ZERGLING, const.ULTRALISK, const.ROACH, const.SPIRE, const.OVERLORDTRANSPORT,
     const.HYDRALISKDEN, const.SPINECRAWLER}

# Placeholder that will hold all army units of all races eventually
ARMY_UNITS = ZERG_ARMY_UNITS

ZERG_UPGRADES_TO_STRUCTURE = {
    const.ZERGMELEEWEAPONSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGMELEEWEAPONSLEVEL2: const.EVOLUTIONCHAMBER,
    const.ZERGMELEEWEAPONSLEVEL3: const.EVOLUTIONCHAMBER,
    const.ZERGGROUNDARMORSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGGROUNDARMORSLEVEL2: const.EVOLUTIONCHAMBER,
    const.ZERGGROUNDARMORSLEVEL3: const.EVOLUTIONCHAMBER,
    const.ZERGMISSILEWEAPONSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGMISSILEWEAPONSLEVEL2: const.EVOLUTIONCHAMBER,
    const.ZERGMISSILEWEAPONSLEVEL3: const.EVOLUTIONCHAMBER,
    const.ZERGFLYERWEAPONSLEVEL1: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGFLYERWEAPONSLEVEL2: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGFLYERWEAPONSLEVEL3: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGFLYERARMORSLEVEL1: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGFLYERARMORSLEVEL2: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGFLYERARMORSLEVEL3: {const.SPIRE, const.GREATERSPIRE},
    const.ZERGLINGMOVEMENTSPEED: const.SPAWNINGPOOL,
    const.ZERGLINGATTACKSPEED: const.SPAWNINGPOOL,
    const.CENTRIFICALHOOKS: const.BANELINGNEST,
    const.GLIALRECONSTITUTION: const.ROACHWARREN,
    const.TUNNELINGCLAWS: const.ROACHWARREN,
    const.EVOLVEMUSCULARAUGMENTS: const.HYDRALISKDEN,
    const.EVOLVEGROOVEDSPINES: const.HYDRALISKDEN,
    const.BURROW: const.HATCHERY,
    const.INFESTORENERGYUPGRADE: const.INFESTATIONPIT,
    const.UpgradeId.OVERLORDSPEED: const.HATCHERY,
    const.CHITINOUSPLATING: const.ULTRALISKCAVERN,
    const.ANABOLICSYNTHESIS: const.ULTRALISKCAVERN,
}

ZERG_UPGRADES_TO_TECH_REQUIREMENT = {
    const.ZERGMELEEWEAPONSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGMELEEWEAPONSLEVEL2: const.ZERGMELEEWEAPONSLEVEL1,
    const.ZERGMELEEWEAPONSLEVEL3: const.ZERGMELEEWEAPONSLEVEL2,
    const.ZERGGROUNDARMORSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGGROUNDARMORSLEVEL2: const.ZERGGROUNDARMORSLEVEL1,
    const.ZERGGROUNDARMORSLEVEL3: const.ZERGGROUNDARMORSLEVEL2,
    const.ZERGMISSILEWEAPONSLEVEL1: const.EVOLUTIONCHAMBER,
    const.ZERGMISSILEWEAPONSLEVEL2: const.ZERGMISSILEWEAPONSLEVEL1,
    const.ZERGMISSILEWEAPONSLEVEL3: const.ZERGMISSILEWEAPONSLEVEL2,
    const.ZERGFLYERWEAPONSLEVEL1: None,
    const.ZERGFLYERWEAPONSLEVEL2: const.ZERGFLYERWEAPONSLEVEL1,
    const.ZERGFLYERWEAPONSLEVEL3: const.ZERGFLYERWEAPONSLEVEL2,
    const.ZERGFLYERARMORSLEVEL1: None,
    const.ZERGFLYERARMORSLEVEL2: const.ZERGFLYERARMORSLEVEL1,
    const.ZERGFLYERARMORSLEVEL3: const.ZERGFLYERARMORSLEVEL2,
    const.ZERGLINGMOVEMENTSPEED: const.SPAWNINGPOOL,
    const.ZERGLINGATTACKSPEED: const.HIVE,
    const.CENTRIFICALHOOKS: const.LAIR,
    const.GLIALRECONSTITUTION: const.LAIR,
    const.TUNNELINGCLAWS: const.LAIR,
    const.EVOLVEMUSCULARAUGMENTS: const.HYDRALISKDEN,
    const.EVOLVEGROOVEDSPINES: const.HYDRALISKDEN,
    const.BURROW: const.HATCHERY,
    const.UpgradeId.OVERLORDSPEED: const.HATCHERY,
    const.INFESTORENERGYUPGRADE: const.INFESTATIONPIT,
    const.CHITINOUSPLATING: const.ULTRALISKCAVERN,
    const.ANABOLICSYNTHESIS: const.ULTRALISKCAVERN,
}

ZERG_UPGRADES = ZERG_UPGRADES_TO_STRUCTURE.keys()

ENEMY_NON_ARMY = \
    {const.OVERLORD, const.OVERSEER}

WORKERS = {const.PROBE, const.DRONE, const.SCV}

NON_COMBATANTS = WORKERS | {const.OVERLORD, const.OVERSEER, const.OBSERVER, const.BROODLING, const.OVERLORDTRANSPORT}

DEFENSIVE_STRUCTURES = {const.BUNKER, const.MISSILETURRET, const.PLANETARYFORTRESS, const.SPINECRAWLER,
                        const.SPORECRAWLER, const.PHOTONCANNON, const.SHIELDBATTERY}

VESPENE_REFINERIES = {const.EXTRACTOR, const.REFINERY, const.ASSIMILATOR}

# Value of army units
# Used when determing whether to attack or not
ZERG_ARMY_VALUE = \
    {const.ZERGLING: 0.4, const.BANELING: 1.25, const.ROACH: 1.5, const.RAVAGER: 2.5, const.HYDRALISK: 2,
     const.MUTALISK: 2, const.OVERSEER: 1, const.INFESTOR: 2.5, const.CORRUPTOR: 2, const.VIPER: 3,
     const.BROODLORD: 4, const.ULTRALISK: 5}

TOWNHALLS = {townhall for subset in sc2.data.race_townhalls.values() for townhall in subset}
UNUPGRADED_TOWNHALLS = {const.HATCHERY, const.NEXUS, const.COMMANDCENTER}

# Attributes
# {'Light': 1, 'Armored': 2, 'Biological': 3, 'Mechanical': 4,
# 'Robotic': 5, 'Psionic': 6, 'Massive': 7, 'Structure': 8, 'Hover': 9,
# 'Heroic': 10, 'Summoned': 11}
ATTRIBUTES = dict(data_pb2.Attribute.items())


# Messages
class Messages(enum.Enum):
    # ENEMY START LOCATION MESSAGES
    OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION = 0  # Message indicating that overlord scout was sent to empty base
    OVERLORD_SCOUT_FOUND_ENEMY_BASE = 1  # Message indicating that the army can't find enemy base
    ARMY_COULDNT_FIND_ENEMY_BASE = 2  # Message indicating that the army can't find enemy base
    ARMY_FOUND_ENEMY_BASE = 3  # Message indicating that the army can't find enemy base

    # ENEMY UNITS FOUND MESSAGES
    OVERLORD_SCOUT_FOUND_ENEMY_DEFENSIVE_STRUCTURES = 4
    OVERLORD_SCOUT_FOUND_ENEMY_PROXY = 5
    OVERLORD_SCOUT_FOUND_ENEMY_RUSH = 6
    OVERLORD_SCOUT_FOUND_ENEMY_WORKER_RUSH = 7
    OVERLORD_SCOUT_FOUND_NO_RUSH = 8
    FOUND_ENEMY_EARLY_AGGRESSION = 9
    FOUND_ENEMY_GREATER_FORCE = 10
    ENEMY_AIR_TECH_SCOUTED = 11
    ENEMY_COUNTER_WITH_ROACHES_SCOUTED = 12
    ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD = 13
    DEFENDING_AGAINST_MULTIPLE_ENEMIES = 14
    ENEMY_MOVING_OUT_SCOUTED = 15

    # STRATEGIC NOTES MESSAGES
    ENEMY_EARLY_NATURAL_EXPAND_TAKEN = 16
    ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN = 17
    NEW_BUILD = 18  # New build added
    NEW_BUILD_STAGE = 19  # New build stage entered

    # UNITS TRAINED MESSAGES
    UNIT_CREATED = 20
    STRUCTURE_COMPLETE = 21
    UPGRADE_STARTED = 22

    # UNIT ORDER MESSAGES
    DRONE_LEAVING_TO_CREATE_HATCHERY = 23  # Value is Drone's tag
    OVERLORD_SCOUT_2_TO_ENEMY_RAMP = 24  # Move the second overlord scout to the enemy's main ramp
    PULL_WORKERS_OFF_VESPENE = 25  # Value is int of workers to mine vespene. None if return to default.
    UNROOT_ALL_SPINECRAWLERS = 26  # Message indicating we should uproot and reposition spinecrawlers

    # STATE MACHINE
    STATE_ENTERED = 27  # Value is State being left
    STATE_EXITED = 28  # Value is State entered
    DONT_DEFEND = 29  # Indicates that we shouldn't ever enter DEFENDING forces state


# Build Manager Commands
class BuildManagerCommands(enum.Enum):
    EXPAND_MOVE = 0  # Command to move to expansion before building
    BUILD_OVERLORD = 1


# Force Manager Commands
class ForceManagerCommands(enum.Enum):
    START_ATTACKING = 0  # When attack has started
    START_RETREATING = 1  # When retreating has started


# Resource Manager Commands
class ResourceManagerCommands(enum.Enum):
    QUEEN_SPAWN_TUMOR = 0
    PULL_WORKERS_OFF_VESPENE = 1


# Force Manager States
class ForcesStates(enum.Enum):
    HOUSEKEEPING = 0  # Default keeping units at home
    ESCORTING = 1  # Guarding drone to expansion
    DEFENDING = 2  # Defending against active threat at home
    MOVING_TO_ATTACK = 3
    ATTACKING = 4
    RETREATING = 5
    SEARCHING = 6


# Overlord Scout States
class OverlordStates(enum.Enum):
    INITIAL = 0  # Initial peek into natural expansion
    INITIAL_BACKOUT = 1  # Rest outside of enemy's natural
    INITIAL_DIVE = 2  # Initial dive into main
    SUICIDE_DIVE = 3  # Dive into enemy's main on a suicide scouting mission
