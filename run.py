import datetime
import importlib
import os
import random
import sys

# Add lib to our path (which holds our sc2-python installation)
sys.path.append('./lib/')

import sc2
from __init__ import run_ladder_game

import lambdanaut.bot as bot

datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")


MAPS = [
    'AutomatonLE',
    'DarknessSanctuaryLE',
    'KairosJunctionLE',
    'ParaSiteLE',
    'CeruleanFallLE',
    'BlueshiftLE',
    'PortAleksanderLE',
    'StasisLE']

MAP_NAME = ""
REALTIME = False
# DIFFICULTY = sc2.Difficulty.CheatInsane
DIFFICULTY = sc2.Difficulty.CheatMoney
# DIFFICULTY = sc2.Difficulty.CheatVision
# DIFFICULTY = sc2.Difficulty.VeryHard
# DIFFICULTY = sc2.Difficulty.Hard
# DIFFICULTY = sc2.Difficulty.Medium
# DIFFICULTY = sc2.Difficulty.Easy
RACE = sc2.Race.Zerg
ENEMY_RACE = sc2.Race.Protoss
REPLAY_NAME = os.path.join("replays", "last_lambdanaut_replay{}.*.sc2replay".format(datetime_str))


if not MAP_NAME:
    MAP_NAME = random.choice(MAPS)


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
            sc2.player.Computer(ENEMY_RACE, DIFFICULTY)
        ]

        gen = sc2.main._host_game_iter(
            sc2.maps.get(MAP_NAME),
            player_config,
            realtime=REALTIME,
            save_replay_as=REPLAY_NAME,
        )

        while True:
            r = next(gen)

            # input("Press enter to reload ")

            print("============================ Reloading LambdaBot =================================")

            importlib.reload(bot)
            player_config[0].ai = bot.LambdaBot()
            gen.send(player_config)

