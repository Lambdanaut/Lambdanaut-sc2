from collections import Counter
import datetime
import itertools
import json
import os
import random
import sys
from typing import List, Tuple

import lib.sc2 as sc2
from lib.sc2.unit import Unit
from lib.sc2.position import Point2
import lib.sc2.constants as const

datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")


MAP_NAME = "training"
TRAINING_MODE = True  # True generates training data. False generates testing data.
CONTINUE_FROM_SAVE_FILE = True
REALTIME = False

DATA_DIR = 'data'

DATA_FILE_TRAINING = os.path.join(DATA_DIR, 'combat.json')
SAVE_FILE_TRAINING = os.path.join(DATA_DIR, 'combat_save.json')

DATA_FILE_TESTING = os.path.join(DATA_DIR, 'combat_testing.json')
SAVE_FILE_TESTING = os.path.join(DATA_DIR, 'combat_testing_save.json')

DATA_FILE = DATA_FILE_TRAINING if TRAINING_MODE else DATA_FILE_TESTING
SAVE_FILE = SAVE_FILE_TRAINING if TRAINING_MODE else SAVE_FILE_TESTING

# Filepaths to combine if --combine-data is passed in as an arg
COMBINE_DATA_FILEPATHS = [
    'combat_zvz.json',
    'combat_zvp.json',
    'combat_zvt.json',
    'combat_zvz_air.json',
    'combat_zvp_air.json',
    'combat_zvt_air.json',
    'combat_zvt_mmm.json',
]
COMBINE_DATA_FILEPATHS = [os.path.join(DATA_DIR, fp) for fp in COMBINE_DATA_FILEPATHS]

COMBINE_DATA_FILEOUT = 'combat_combined.json'


RACE = sc2.Race.Zerg

# Values to use in random.expovariate(value) to generate random unit counts
UNIT_COUNT_EXPLICIT = [0.2, 0.05]
UNIT_TESTING_COUNT_EXPLICIT = [0.02]

if not TRAINING_MODE:
    UNIT_COUNT_EXPLICIT = UNIT_TESTING_COUNT_EXPLICIT


UNIT_TYPES_ZERG = [const.SPINECRAWLER, const.HYDRALISK, const.QUEEN, const.RAVAGER, const.ROACH, const.ULTRALISK, const.ZERGLING,
                   const.BANELING]
UNIT_TYPES_TERRAN = [const.SIEGETANKSIEGED, const.THOR, const.SIEGETANK, const.CYCLONE, const.MARINE, const.MARAUDER, const.REAPER,
                     const.HELLION, const.HELLIONTANK]

UNIT_TYPES_PROTOSS = [const.COLOSSUS, const.IMMORTAL, const.STALKER, const.ADEPT, const.ARCHON,
                      const.ZEALOT]

UNIT_TYPES_AIR_ZERG = [const.SPORECRAWLER, const.QUEEN, const.HYDRALISK, const.MUTALISK, const.CORRUPTOR, const.BROODLORD]
UNIT_TYPES_AIR_TERRAN = [const.VIKING, const.MARINE, const.BANSHEE, const.THOR, const.CYCLONE,
                         const.BATTLECRUISER,]
UNIT_TYPES_AIR_PROTOSS = [const.STALKER, const.PHOENIX, const.VOIDRAY, const.TEMPEST, const.CARRIER,
                          const.MOTHERSHIP]

UNIT_TYPES_MMM_TERRAN = [const.MARINE, const.MARAUDER, const.MEDIVAC]

UNIT_TYPES_P1 = None
UNIT_TYPES_P2 = None


if not UNIT_TYPES_P1 and not UNIT_TYPES_P2:
    BUILDS_TO_GENERATE = [
        (UNIT_TYPES_ZERG, UNIT_TYPES_ZERG),
        (UNIT_TYPES_ZERG, UNIT_TYPES_TERRAN),
        (UNIT_TYPES_ZERG, UNIT_TYPES_PROTOSS),
        (UNIT_TYPES_AIR_ZERG, UNIT_TYPES_AIR_ZERG),
        (UNIT_TYPES_AIR_ZERG, UNIT_TYPES_AIR_TERRAN),
        (UNIT_TYPES_AIR_ZERG, UNIT_TYPES_AIR_PROTOSS),
        (UNIT_TYPES_ZERG, UNIT_TYPES_MMM_TERRAN),
    ]
else:
    BUILDS_TO_GENERATE = [(UNIT_TYPES_P1, UNIT_TYPES_P2)]


class TrainingBot(sc2.BotAI):
    def __init__(self):
        super(TrainingBot, self).__init__()

        self.training_loop = 0

        # Get permutations of unit counts to train against
        # Data should be in format:
        #  [ [( ( (Z, 3), (B, 1)... ), ( (Z, 10), (B, 0) ) ), ...] ]
        # The above example represents:
        #   3 zerglings 1 baneling vs 10 zerglings 0 banelings
        #
        self.training_sets = [self.create_training_set(set_1, set_2)
                              for set_1, set_2 in BUILDS_TO_GENERATE]
        self.training_set = self.training_sets[0]

        self.build_i = 0

        # Record combat
        self.combat_record = []

    async def on_step(self, iteration):
        # Load from a save file
        if iteration == 0:
            if CONTINUE_FROM_SAVE_FILE:
                self.load_save_file(SAVE_FILE, DATA_FILE)
                print("Continuing from save file starting at iteration: `{}`".
                      format(self.training_loop))

        units = self.units()
        enemy = self.enemy_units()

        if self.training_loop < len(self.training_set):
            if not units or not enemy:
                self.record_result()

                # Clean up
                if units | enemy:
                    await self._client.debug_kill_unit(units | enemy)

                await self.spawn_iteration_units()
                self.iterate()

            else:
                # Test to see if we have a draw condition in which neither player
                # can attack each other
                units_can_attack_ground = units.filter(lambda u: u.can_attack_ground)
                units_can_attack_air = units.filter(lambda u: u.can_attack_air)
                enemy_can_attack_ground = enemy.filter(lambda u: u.can_attack_ground)
                enemy_can_attack_air = enemy.filter(lambda u: u.can_attack_air)

                units_air = units.flying
                units_ground = units.not_flying
                enemy_air = enemy.flying
                enemy_ground = enemy.not_flying

                draw_flag_p1 = False
                draw_flag_p2 = False

                if not units_can_attack_ground:
                    if enemy_ground:
                        draw_flag_p1 = True
                if not units_can_attack_air:
                    if enemy_air:
                        draw_flag_p1 = True
                if not enemy_can_attack_ground:
                    if units_ground:
                        draw_flag_p2 = True
                if not enemy_can_attack_air:
                    if units_air:
                        draw_flag_p2 = True

                if draw_flag_p1 or draw_flag_p2:
                    # Don't record this result. Don't want to flood data with too many weird draws
                    # self.record_result()
                    print('Draw. Not recording result')

                    # Clean up
                    if units | enemy:
                        await self._client.debug_kill_unit(units | enemy)

                    await self.spawn_iteration_units()
                    self.iterate()

        else:

            if self.build_i == len(self.training_sets) - 1:
                print("===========TRAINING COMPLETED===========")
                print("Saving training data to `{}`".format(DATA_FILE))

                if units | enemy:
                    # Cleanup remaining units
                    await self._client.debug_kill_unit(units | enemy)

                # Save data
                self.save_training_data(DATA_FILE)

                # Reset save file
                self.save_save_file(SAVE_FILE, training_loop=0, build_i=0)

                sys.exit()

            else:
                # Next training set
                self.build_i += 1
                self.training_loop = 0
                self.training_set = self.training_sets[self.build_i]

    def iterate(self):
        print("TRAINING ITERATION: {} / {} of build {}".format(
            self.training_loop, len(self.training_set), self.build_i))

        # Save the ongoing combat record
        if self.training_loop % 5 == 1:
            self.save_save_file(SAVE_FILE)
            self.save_training_data(DATA_FILE)

        self.training_loop += 1

    async def spawn_iteration_units(self):
        training_set = self.get_training_set()

        p1_units = training_set[0]
        p2_units = training_set[1]

        print("P1: {}".format(p1_units))
        print("P2: {}".format(p2_units))

        p1_position = self._game_info.map_center - sc2.position.Point2((-6, 0))
        p2_position = self._game_info.map_center - sc2.position.Point2((+6, 0))

        # Create player 1 units
        await self.create_units(p1_units, p1_position, 1)

        # Create player 2 units
        await self.create_units(p2_units, p2_position, 2)

    async def create_units(self, build_set: Tuple[Tuple[Unit, int]], position: Point2, player):
        """
        Spawns units, given a build set
        """
        for unit, unit_count in build_set:
            if unit_count:
                await self._client.debug_create_unit([[unit, unit_count, position, player]])

    def get_training_set(self):
        return self.training_set[self.training_loop]

    def create_training_set(self, unit_types1, unit_types2) -> List[Tuple[Tuple[Tuple[Unit, int]]]]:
        # Get unit counts
        unit_counts = UNIT_COUNT_EXPLICIT

        # 2D Lists of Unit types combined with count
        # [[(Z, 0), (Z, 1), (Z, 2)], [(B, 0), (B, 1)..]]
        training_set_counts1: List[List[Tuple[Unit, int]]] = \
            [[(unit, i) for i in unit_counts] for unit in unit_types1]
        training_set_counts2: List[List[Tuple[Unit, int]]] = \
            [[(unit, i) for i in unit_counts] for unit in unit_types2]

        # Permute the lists of units together and flatten it
        # [ ( (Z, 0), (B, 0), ), ( (Z, 1), (B, 0 ) )... ( (Z, 10), (B, 10) ) ... ]
        training_set_builds1: List[Tuple[Tuple[Unit, int]]] = self.to_training_set_builds(training_set_counts1)
        training_set_builds2: List[Tuple[Tuple[Unit, int]]] = self.to_training_set_builds(training_set_counts2)

        def is_viable(build: Tuple[Tuple[Unit, int]]) -> bool:
            """
            Function that returns false if the build has more unit types than allowed

            If we allow 3 unit types, then this would return true:
                ((Z, 2), (B, 2) (R, 2), (H, 0))
            But this would return false:
                ((Z, 1), (B, 1) (R, 1), (H, 1))
            """
            max_unit_types_allowed = 3
            unit_types_counted = 0
            for unit, count in build:
                if count:
                    unit_types_counted += 1

            return max_unit_types_allowed >= unit_types_counted

        # Remove builds that have too many unit types in them. Don't have crazy unit compositions.
        training_set_builds1 = [build for build in training_set_builds1 if is_viable(build)]
        training_set_builds2 = [build for build in training_set_builds2 if is_viable(build)]

        # Permute the unit count builds together to form builds for p1 and p2 builds
        # Example of P1 having 1 zergling and P2 having 1 baneling:
        # [ ( ( (Z, 1), (B, 0), ), ( (Z, 0),  (B, 1 ) ), ... ]
        training_set: List[Tuple[Tuple[Tuple[Unit, int]]]] = list(
            itertools.product(training_set_builds1, training_set_builds2))

        # Remove blank unit sets. We don't want to face an army against 0 units.
        training_set = [
            (p1, p2) for p1, p2 in training_set
            if any([unit[1] for unit in p1]) and any([unit[1] for unit in p2])
        ]

        # Remove duplicate unit sets. We don't want two zergling(or other unit type) groups together for one player
        training_set = [
            (p1, p2) for p1, p2 in training_set
            if all([p1[unit_i][0] not in [u[0] for u in p1[unit_i + 1:] ] for unit_i in range(len(p1)) ]) and
               all([p2[unit_i][0] not in [u[0] for u in p2[unit_i + 1:] ] for unit_i in range(len(p2)) ])
        ]

        # Mutate the unit counts to be exponential variants
        training_set = [tuple(tuple((u, max(1, round(random.expovariate(count)))) for u, count in build)
                              for build in matchup)
                        for matchup in training_set]

        return training_set

    def to_training_set_builds(self, training_set_counts: List[List[Tuple[Unit, int]]])\
            -> List[Tuple[Tuple[Unit, int]]]:
        """
        Permute the lists of units together and flatten it
        Output:
            [  ( (Z, 0), (B, 0), ), ( (Z, 1), (B, 0 ) )... ( (Z, 10), (B, 10) ) ... ]
        """
        training_set_builds_unflat = []
        for i in range(len(training_set_counts)):
            for i2 in range(i + 1, len(training_set_counts)):
                build = list(itertools.product(training_set_counts[i], training_set_counts[i2]))
                training_set_builds_unflat.append(build)

        # Flatten the training set builds
        training_set_builds = [y for x in training_set_builds_unflat for y in x]

        return training_set_builds

    def record_result(self):
        units = self.units()
        enemy = self.enemy_units()
        training_set = self.get_training_set()

        winner = 0  # Draw condition
        win_ratio = 1.0
        if units and not enemy:
            winner = 1  # Player 1
            training_build = training_set[0]
            unit_count = sum([unit[1] for unit in training_build])
            win_ratio = len(units.of_type([unit[0] for unit in training_build])) / unit_count
        if enemy and not units:
            winner = 2  # Player 2
            training_build = training_set[1]
            unit_count = sum([unit[1] for unit in training_build])
            win_ratio = len(enemy.of_type([unit[0] for unit in training_build])) / unit_count

        win_ratio = min(1.0, win_ratio)

        print('WINNER: p{}'.format(winner))
        print('WIN RATIO: {}'.format(win_ratio))

        if win_ratio < 0.00001:
            # Weird case. Return without recording result
            print('Low win ratio. Not recording result. ')
            return

        training_set = self.get_training_set()
        p1_units = training_set[0]
        p2_units = training_set[1]

        p1_units_dict = Counter()
        p2_units_dict = Counter()

        # Wrap in dictionary
        for unit, unit_count in p1_units:
            p1_units_dict[unit.value] += unit_count
        for unit, unit_count in p2_units:
            p2_units_dict[unit.value] += unit_count

        result = {'1': p1_units_dict, '2': p2_units_dict, 'result': winner, 'win_ratio': win_ratio}

        self.combat_record.append(result)

    def randomize_results(self):
        """Randomize combat results so it doesn't look like the same player won every match. """

        for record in self.combat_record:
            if random.randint(0, 1):
                result = record['result']

                if result != 0:
                    p1 = record['1']
                    p2 = record['2']

                    record['result'] = 1 if result == 2 else 2
                    record['1'] = p2
                    record['2'] = p1

    def save_training_data(self, filepath):

        self.randomize_results()

        if self.combat_record:
            json_combat_record = json.dumps(self.combat_record)

            with open(filepath, 'w') as f:
                f.write(json_combat_record)

    def save_save_file(self, filepath, training_loop=None, build_i=None):
        training_loop = self.training_loop if training_loop is None else training_loop
        build_i = self.build_i if build_i is None else build_i

        save_data = [training_loop, build_i]

        json_save_loop = json.dumps(save_data)

        with open(filepath, 'w') as f:
            f.write(json_save_loop)

    def load_save_file(self, save_filepath, training_data_filepath=None):
        with open(save_filepath, 'r') as f:
            contents = f.read()
            loaded = json.loads(contents)

        self.training_loop, self.build_i = loaded
        self.training_set = self.training_sets[self.build_i]

        if training_data_filepath:
            with open(training_data_filepath, 'r') as f:
                contents = f.read()
                if not contents:
                    print("No training data. Starting from iteration 0.")
                    self.training_loop = 0
                    return
                loaded = json.loads(contents)

            self.combat_record = loaded


def combine_data(filepaths, out_filepath):
    data = []

    for filepath in filepaths:
        with open(filepath, 'r') as f:
            contents = f.read()
            if not contents:
                print("Error reading file {}".format(filepath))
                return
            loaded = json.loads(contents)
            data += loaded

    with open(out_filepath, 'w') as f:
        f.write(json.dumps(data))

    return True


def main():
    print("Starting local game...")

    if '--combine-data' in sys.argv:
        combine_data(COMBINE_DATA_FILEPATHS, COMBINE_DATA_FILEOUT)
        return

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

