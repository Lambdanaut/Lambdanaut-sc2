"""
Class to add further constants from data_pb2
"""

import enum

import sc2
import sc2.constants as const
from s2clientprotocol import data_pb2

# About number of frames per second on faster speed
FPS = 22

# Set of zerg structures built from drones
ZERG_STRUCTURES_FROM_DRONES = \
    (const.HATCHERY, const.SPAWNINGPOOL, const.EXTRACTOR, const.EVOLUTIONCHAMBER, const.SPORECRAWLER,
     const.BANELINGNEST, const.ROACHWARREN, const.SPINECRAWLER, const.SPIRE, const.NYDUSNETWORK,
     const.INFESTATIONPIT, const.HYDRALISKDEN, const.ULTRALISKCAVERN,)

ZERG_UNITS_FROM_LARVAE = \
    (const.DRONE, const.OVERLORD, const.ZERGLING, const.ROACH, const.HYDRALISK,
     const.MUTALISK, const.CORRUPTOR, const.ULTRALISK,)

ZERG_ARMY_UNITS = \
    (const.ZERGLING, const.BANELING, const.ROACH, const.RAVAGER, const.HYDRALISK, const.MUTALISK, const.OVERSEER,
     const.INFESTOR, const.CORRUPTOR, const.VIPER, const.BROODLORD, const.ULTRALISK,)

ZERG_UPGRADES_TO_ABILITY = {
    const.ZERGMELEEWEAPONSLEVEL1: const.RESEARCH_ZERGMELEEWEAPONSLEVEL1,
    const.ZERGMELEEWEAPONSLEVEL2: const.RESEARCH_ZERGMELEEWEAPONSLEVEL2,
    const.ZERGMELEEWEAPONSLEVEL3: const.RESEARCH_ZERGMELEEWEAPONSLEVEL3,
    const.ZERGGROUNDARMORSLEVEL1: const.RESEARCH_ZERGGROUNDARMORLEVEL1,
    const.ZERGGROUNDARMORSLEVEL2: const.RESEARCH_ZERGGROUNDARMORLEVEL2,
    const.ZERGGROUNDARMORSLEVEL3: const.RESEARCH_ZERGGROUNDARMORLEVEL3,
    const.ZERGMISSILEWEAPONSLEVEL1: const.RESEARCH_ZERGMISSILEWEAPONSLEVEL1,
    const.ZERGMISSILEWEAPONSLEVEL2: const.RESEARCH_ZERGMISSILEWEAPONSLEVEL2,
    const.ZERGMISSILEWEAPONSLEVEL3: const.RESEARCH_ZERGMISSILEWEAPONSLEVEL3,
    const.ZERGFLYERWEAPONSLEVEL1: const.RESEARCH_ZERGFLYERATTACKLEVEL1,
    const.ZERGFLYERWEAPONSLEVEL2: const.RESEARCH_ZERGFLYERATTACKLEVEL2,
    const.ZERGFLYERWEAPONSLEVEL3: const.RESEARCH_ZERGFLYERATTACKLEVEL3,
    const.ZERGFLYERARMORSLEVEL1: const.RESEARCH_ZERGFLYERARMORLEVEL1,
    const.ZERGFLYERARMORSLEVEL2: const.RESEARCH_ZERGFLYERARMORLEVEL2,
    const.ZERGFLYERARMORSLEVEL3: const.RESEARCH_ZERGFLYERARMORLEVEL3,
    const.ZERGLINGMOVEMENTSPEED: const.RESEARCH_ZERGLINGMETABOLICBOOST,
    const.CENTRIFICALHOOKS: const.RESEARCH_CENTRIFUGALHOOKS,
    const.GLIALRECONSTITUTION: const.RESEARCH_GLIALREGENERATION,
    const.EVOLVEMUSCULARAUGMENTS: const.RESEARCH_MUSCULARAUGMENTS,
    const.EVOLVEGROOVEDSPINES: const.RESEARCH_GROOVEDSPINES,
}

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
    const.ZERGFLYERWEAPONSLEVEL1: const.SPIRE,
    const.ZERGFLYERWEAPONSLEVEL2: const.SPIRE,
    const.ZERGFLYERWEAPONSLEVEL3: const.SPIRE,
    const.ZERGFLYERARMORSLEVEL1: const.SPIRE,
    const.ZERGFLYERARMORSLEVEL2: const.SPIRE,
    const.ZERGFLYERARMORSLEVEL3: const.SPIRE,
    const.ZERGLINGMOVEMENTSPEED: const.SPAWNINGPOOL,
    const.CENTRIFICALHOOKS: const.BANELINGNEST,
    const.GLIALRECONSTITUTION: const.ROACHWARREN,
    const.EVOLVEMUSCULARAUGMENTS: const.HYDRALISKDEN,
    const.EVOLVEGROOVEDSPINES: const.HYDRALISKDEN,
}

ENEMY_NON_ARMY = \
    {const.OVERLORD, const.OVERSEER}


# Value of different armies
ZERG_ARMY_VALUE = \
    {const.ZERGLING: 1, const.BANELING: 4, const.ROACH: 4, const.RAVAGER: 5, const.HYDRALISK: 5, const.MUTALISK: 5,
     const.OVERSEER: 5, const.INFESTOR: 7, const.CORRUPTOR: 7, const.VIPER: 7, const.BROODLORD: 15, const.ULTRALISK: 15}

TERRAN_ARMY_VALUE = \
    {const.MARINE: 4, const.REAPER: 5, const.MARAUDER: 9, const.HELLION: 10, const.WIDOWMINE: 7, const.SIEGETANK: 20}

TERRAN_ARMY_VALUE = \
    {}


TOWNHALLS = {townhall for subset in sc2.data.race_townhalls.values() for townhall in subset}

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

    # STRATEGIC NOTES MESSAGES
    ENEMY_EARLY_NATURAL_EXPAND_TAKEN = 5
    ENEMY_EARLY_NATURAL_EXPAND_NOT_TAKEN = 6


# Build Manager Commands
class BuildManagerCommands(enum.Enum):
    EXPAND_MOVE = 0  # Command to move to expansion before building
    BUILD_OVERLORD = 1


# Resource Manager Commands
class ResourceManagerCommands(enum.Enum):
    QUEEN_SPAWN_TUMOR = 0


# Force Manager States
class ForcesStates(enum.Enum):
    HOUSEKEEPING = 0  # Default keeping units at home
    DEFENDING = 1  # Defending against active threat at home
    MOVING_TO_ATTACK = 2
    ATTACKING = 3
    SEARCHING = 4


# Overlord Scout States
class OverlordStates(enum.Enum):
    INITIAL = 0  # Initial peek into natural expansion
    INITIAL_BACKOUT = 1  # Rest outside of enemy's natural
    INITIAL_DIVE = 2  # Initial dive into main
    SUICIDE_DIVE = 3  # Dive into enemy's main on a suicide scouting mission
