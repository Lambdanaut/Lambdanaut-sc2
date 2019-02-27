import datetime
import os
import random
import sys

import lib.sc2 as sc2
from __init__ import run_ladder_game

import lambdanaut
import lambdanaut.bot as bot

datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")


BUILDS = [
    sc2.AIBuild.RandomBuild,
    sc2.AIBuild.Rush,
    sc2.AIBuild.Timing,
    sc2.AIBuild.Power,
    sc2.AIBuild.Macro,
    sc2.AIBuild.Air, ]
MAPS = [
    'AutomatonLE',
    'DarknessSanctuaryLE',
    'KairosJunctionLE',
    'ParaSiteLE',
    'CeruleanFallLE',
    'BlueshiftLE',
    'PortAleksanderLE', ]

MAP_NAME = "PortAleksanderLE"
MICRO_MAP_NAME = "kairo_training"
REALTIME = False

# BUILD = sc2.AIBuild.RandomBuild
# BUILD = sc2.AIBuild.Rush
BUILD = sc2.AIBuild.Timing
# BUILD = sc2.AIBuild.Power
# BUILD = sc2.AIBuild.Macro
# BUILD = sc2.AIBuild.Air

# DIFFICULTY = sc2.Difficulty.CheatInsane
# DIFFICULTY = sc2.Difficulty.CheatMoney
# DIFFICULTY = sc2.Difficulty.CheatVision
DIFFICULTY = sc2.Difficulty.VeryHard
# DIFFICULTY = sc2.Difficulty.Hard
# DIFFICULTY = sc2.Difficulty.Medium
# DIFFICULTY = sc2.Difficulty.Easy

RACE = sc2.Race.Zerg
ENEMY_RACE = sc2.Race.Protoss
REPLAY_NAME = os.path.join("replays", "last_lambdanaut_replay{}.*.sc2replay".format(datetime_str))

if not MAP_NAME:
    MAP_NAME = random.choice(MAPS)
if not BUILD:
    BUILD = random.choice(BUILDS)

TESTING_MICRO = lambdanaut.CREATE_DEBUG_UNITS
if TESTING_MICRO:
    MAP_NAME = MICRO_MAP_NAME


# Start game
if __name__ == '__main__':
    if "--LadderServer" in sys.argv:
        # Ladder game started by LadderManager
        ladder_bot = sc2.player.Bot(RACE, bot.LambdaBot())
        print("Starting ladder game...")
        result, opponentid = run_ladder_game(ladder_bot)
        print(result," against opponent ", opponentid)

    else:
        # Local game
        print("Starting local game...")

        player_config = [
            sc2.player.Bot(RACE, bot.LambdaBot()),
            sc2.player.Computer(ENEMY_RACE, DIFFICULTY, BUILD)
        ]

        sc2.run_game(
            sc2.maps.get(MAP_NAME),
            player_config,
            realtime=REALTIME,
            save_replay_as=REPLAY_NAME)
