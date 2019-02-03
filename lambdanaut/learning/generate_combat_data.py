import datetime
import itertools
import json
import os

import sc2
import sc2.constants as const
import torch

datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")


MAP_NAME = "training"
REALTIME = False
DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'combat.json')

RACE = sc2.Race.Zerg
UNIT_COUNT_EACH = 50


class TrainingBot(sc2.BotAI):
    def __init__(self):
        super(TrainingBot, self).__init__()

        # List of actions to perform each step
        self.actions = []

        self.training_loop = 0

        # Get permutations of unit counts to train against
        self.training_set_counts = list(itertools.combinations(range(1, UNIT_COUNT_EACH), 2))

        # Record combat
        self.combat_record = []

    async def on_step(self, iteration):
        units = self.units()
        enemy = self.known_enemy_units()

        # Order units to attack center
        for unit in units.idle:
            self.actions.append(unit.attack(self.game_info.map_center))

        if self.training_loop < len(self.training_set_counts):
            if not units or not enemy:
                self.record_result()

                # Clean up
                if units | enemy:
                    await self._client.debug_kill_unit(units | enemy)

                await self.iterate()

        else:
            print("===========TRAINING COMPLETED===========")
            print("Saving training data to `{}`".format(DATA_FILE))

            # Cleanup remaining units
            await self._client.debug_kill_unit(units | enemy)

            # Save data
            self.save_training_data(DATA_FILE)

            import pdb; pdb.set_trace()

        # Do these actions each step
        await self.do_actions(self.actions)
        self.actions = []

    async def iterate(self):
        print("TRAINING ITERATION: {}".format(self.training_loop))

        training_set_counts = self.get_training_set()
        self.training_loop += 1

        unit = const.ZERGLING
        p1_unit_count = training_set_counts[0]
        p2_unit_count = training_set_counts[1]

        print("P1: {}".format(p1_unit_count))
        print("P2: {}".format(p2_unit_count))

        p1_position = self._game_info.map_center - sc2.position.Point2((-5, 0))
        p2_position = self._game_info.map_center - sc2.position.Point2((+5, 0))

        # Create player 1 units
        await self._client.debug_create_unit([[unit, p1_unit_count, p1_position, 1]])

        # Create player 2 units
        await self._client.debug_create_unit([[unit, p2_unit_count, p2_position, 2]])

    def get_training_set(self):
        return self.training_set_counts[self.training_loop]

    def record_result(self):
        units = self.units()
        enemy = self.known_enemy_units()

        winner = 0  # Draw condition
        if units:
            winner = 1  # Player 1
        elif enemy:
            winner = 2  # Player 2

        training_set_counts = self.get_training_set()
        unit_value = const.ZERGLING.value
        p1_unit_count = training_set_counts[0]
        p2_unit_count = training_set_counts[1]

        # Wrap in dictionary
        p1_unit_counts = {unit_value: p1_unit_count}
        p2_unit_counts = {unit_value: p2_unit_count}

        result = {1: p1_unit_counts, 2: p2_unit_counts, 'result': winner}

        self.combat_record.append(result)

    def save_training_data(self, filepath):
        json_combat_record = json.dumps(self.combat_record)

        with open(filepath, 'w') as f:
            f.write(json_combat_record)


def main():
    print("Starting local game...")

    player_config = [
        sc2.player.Bot(RACE, TrainingBot()),
        sc2.player.Computer(RACE)
    ]

    gen = sc2.main._host_game_iter(
        sc2.maps.get(MAP_NAME),
        player_config,
        realtime=REALTIME)

    while True:
        r = next(gen)

        # input("Press enter to reload ")

        print("============================ Reloading Training Bot =================================")

        player_config[0].ai = TrainingBot()
        gen.send(player_config)


# Start game
if __name__ == '__main__':
    main()

