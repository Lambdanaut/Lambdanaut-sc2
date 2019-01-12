import datetime
import importlib
import os
import sys

import sc2
from __init__ import run_ladder_game
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

# Lib holds
sys.path.append('lib/')

import lambdanaut.bot as bot


datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")

REALTIME = False
DIFFICULTY = sc2.Difficulty.VeryHard
#(4)DarknessSanctuaryLE
MAP_NAME = "(4)DarknessSanctuaryLE"
MAP = sc2.maps.get(MAP_NAME)
RACE = Race.Zerg
REPLAY_NAME = os.path.join("replays", "last_lambdanaut_replay{}.*.sc2replay".format(datetime_str))
AGAINST_BOT = True


opponent = sc2.player.Computer(Race.Terran, DIFFICULTY),
if AGAINST_BOT:
    from Overmind.Overmind import Overmind
    opponent = Bot(Race.Zerg, Overmind())

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
            opponent,
        ]

        gen = sc2.main._host_game_iter(
            MAP,
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

