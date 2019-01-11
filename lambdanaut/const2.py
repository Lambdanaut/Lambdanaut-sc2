"""
Class to add further constants from data_pb2

examples: https://github.com/Dentosal/python-sc2/blob/master/sc2/data.py

"""

import sc2.constants as const
from s2clientprotocol import data_pb2


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

ZERG_ARMY_VALUE = \
    {const.ZERGLING: 2, const.BANELING: 8, const.ROACH: 8, const.RAVAGER: 10, const.HYDRALISK: 10, const.MUTALISK: 15,
     const.OVERSEER: 10, const.INFESTOR: 15, const.CORRUPTOR: 15, const.VIPER: 15,
     const.BROODLORD: 35, const.ULTRALISK: 35}


# Attributes
# {'Light': 1, 'Armored': 2, 'Biological': 3, 'Mechanical': 4,
# 'Robotic': 5, 'Psionic': 6, 'Massive': 7, 'Structure': 8, 'Hover': 9,
# 'Heroic': 10, 'Summoned': 11}
ATTRIBUTES = dict(data_pb2.Attribute.items())



# Build order constants
RECENT_EXPAND_MOVE_COMMAND = 'RECENT_EXPAND_MOVE_COMMAND'  # Command to move to expansion before building