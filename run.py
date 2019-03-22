import datetime
import os
import random
import sys

import lib.sc2 as sc2
from __init__ import run_ladder_game

import lambdanaut
import lambdanaut.bot as bot
from lambdanaut.builds import Builds

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

MAP_NAME = "KairosJunctionLE"
MICRO_MAP_NAME = "kairo_training"
VS_HUMAN = False
VS_BOT = False
REALTIME = False

BUILD = None
BUILD = sc2.AIBuild.RandomBuild
# BUILD = sc2.AIBuild.Rush
# BUILD = sc2.AIBuild.Timing
# BUILD = sc2.AIBuild.Power
# BUILD = sc2.AIBuild.Macro
# BUILD = sc2.AIBuild.Air

# DIFFICULTY = sc2.Difficulty.CheatInsane
DIFFICULTY = sc2.Difficulty.CheatMoney
# DIFFICULTY = sc2.Difficulty.CheatVision
# DIFFICULTY = sc2.Difficulty.VeryHard
# DIFFICULTY = sc2.Difficulty.Hard
# DIFFICULTY = sc2.Difficulty.Medium
# DIFFICULTY = sc2.Difficulty.Easy

RACE = sc2.Race.Zerg
ENEMY_RACE = sc2.Race.Zerg
REPLAY_NAME = os.path.join("replays", "last_lambdanaut_replay{}.*.sc2replay".format(datetime_str))

if not MAP_NAME:
    MAP_NAME = random.choice(MAPS)
if not BUILD:
    BUILD = random.choice(BUILDS)

TESTING_MICRO = lambdanaut.CREATE_DEBUG_UNITS
if TESTING_MICRO:
    MAP_NAME = MICRO_MAP_NAME

if VS_BOT:
    from lib.examples.zerg.zerg_rush import ZergRushBot
    from lib.examples.terran.mass_reaper import MassReaperBot
    from lib.examples.worker_rush import WorkerRushBot

    KWARGS = {'additional_builds': [Builds.EARLY_GAME_HATCHERY_FIRST_LING_RUSH]}
    OPPONENT_BOT = bot.Lambdanaut(**KWARGS)

    # OPPONENT_BOT = ZergRushBot()
    # OPPONENT_BOT = MassReaperBot()
    OPPONENT_BOT = WorkerRushBot()


# Start game
if __name__ == '__main__':
    if "--LadderServer" in sys.argv:
        # Ladder game started by LadderManager
        ladder_bot = sc2.player.Bot(RACE, bot.Lambdanaut())
        print("Starting ladder game...")
        result, opponentid = run_ladder_game(ladder_bot)
        print(result," against opponent ", opponentid)

    else:
        # Local game
        print("Starting local game...")

        bot_config = sc2.player.Bot(RACE, bot.Lambdanaut())

        if VS_HUMAN:
            opponent_config = sc2.player.Human(ENEMY_RACE)
            # Reverse player_config so that we can play as human
            player_config = [
                opponent_config,
                bot_config,
            ]
        elif VS_BOT:
            opponent_config = sc2.player.Bot(ENEMY_RACE, OPPONENT_BOT)
            player_config = [
                bot_config,
                opponent_config,
            ]
        else:
            opponent_config = sc2.player.Computer(ENEMY_RACE, DIFFICULTY, BUILD)
            player_config = [
                bot_config,
                opponent_config,
            ]

        sc2.run_game(
            sc2.maps.get(MAP_NAME),
            player_config,
            realtime=REALTIME,
            save_replay_as=REPLAY_NAME)
