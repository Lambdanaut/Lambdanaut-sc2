import importlib
import sys

import sc2, sys
from __init__ import run_ladder_game
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

# Lib holds
sys.path.append('lib/')

import lambdanaut.bot as bot



REALTIME = False
DIFFICULTY = sc2.Difficulty.VeryHard
MAP_NAME = "(2)16-BitLE"
MAP = sc2.maps.get(MAP_NAME)
RACE = Race.Zerg


# Start game
if __name__ == '__main__':
    if "--LadderServer" in sys.argv:
        # Ladder game started by LadderManager
        bot = Bot(RACE, bot.LambdaBot())
        print("Starting ladder game...")
        result, opponentid = run_ladder_game(bot)
        print(result," against opponent ", opponentid)

    else:
        # Local game
        print("Starting local game...")

        player_config = [
            sc2.player.Bot(RACE, bot.LambdaBot()),
            sc2.player.Computer(Race.Protoss, DIFFICULTY),
        ]

        gen = sc2.main._host_game_iter(
            MAP,
            player_config,
            realtime=REALTIME
        )

        while True:
            r = next(gen)

            # input("Press enter to reload ")

            print("============================ Reloading LambdaBot =================================")

            importlib.reload(bot)
            player_config[0].ai = bot.LambdaBot()
            gen.send(player_config)

