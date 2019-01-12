"""
Class to add further constants from data_pb2
"""

import enum

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

ENEMY_NON_ARMY = \
    {const.OVERLORD, const.OVERSEER}




# Value of different armies
ZERG_ARMY_VALUE = \
    {const.ZERGLING: 2, const.BANELING: 8, const.ROACH: 8, const.RAVAGER: 10, const.HYDRALISK: 10, const.MUTALISK: 15,
     const.OVERSEER: 10, const.INFESTOR: 15, const.CORRUPTOR: 15, const.VIPER: 15, const.BROODLORD: 35, const.ULTRALISK: 35}

TERRAN_ARMY_VALUE = \
    {const.MARINE: 4, const.REAPER: 5, const.MARAUDER: 9, const.HELLION: 10, const.WIDOWMINE: 7, const.SIEGETANK: 20}

TERRAN_ARMY_VALUE = \
    {}

# Attributes
# {'Light': 1, 'Armored': 2, 'Biological': 3, 'Mechanical': 4,
# 'Robotic': 5, 'Psionic': 6, 'Massive': 7, 'Structure': 8, 'Hover': 9,
# 'Heroic': 10, 'Summoned': 11}
ATTRIBUTES = dict(data_pb2.Attribute.items())


# Messages
class Messages(enum.Enum):
    OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION = 0  # Message indicating that overlord scout was sent to empty base
    OVERLORD_SCOUT_FOUND_ENEMY_BASE = 1  # Message indicating that the army can't find enemy base
    ARMY_COULDNT_FIND_ENEMY_BASE = 2  # Message indicating that the army can't find enemy base
    ARMY_FOUND_ENEMY_BASE = 3  # Message indicating that the army can't find enemy base


# Build Manager Commands
class BuildManagerCommands(enum.Enum):
    EXPAND_MOVE = 0  # Command to move to expansion before building


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
