"""
For testing different micro code
"""

from collections import Counter
import datetime
import itertools
import sys
from typing import List, Tuple

import sc2
from sc2.unit import Unit
from sc2.position import Point2
import sc2.constants as const

datetime_str = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M")


MAP_NAME = "micro"
REALTIME = True
RACE = sc2.Race.Zerg

# Values to use in random.expovariate(value) to generate random unit counts
UNIT_COUNT_EXPLICIT = [15]

UNIT_TYPES_ZERG = [const.ZERGLING, const.ZERGLING, const.ZERGLING, const.ZERGLING]

UNIT_TYPES_P1 = UNIT_TYPES_ZERG
UNIT_TYPES_P2 = UNIT_TYPES_ZERG


class TrainingBot(sc2.BotAI):
    def __init__(self):
        super(TrainingBot, self).__init__()

        self.training_loop = -1

        # Get permutations of unit counts to train against
        # Data should be in format:
        #  [ [( ( (Z, 3), (B, 1)... ), ( (Z, 10), (B, 0) ) ), ...] ]
        # The above example represents:
        #   3 zerglings 1 baneling vs 10 zerglings 0 banelings
        #
        self.training_sets = [self.create_training_set(UNIT_TYPES_P1, UNIT_TYPES_P2)]

        self.training_set = self.training_sets[0]

        self.build_i = 0

        # Record combat
        self.combat_record = []

        # Actions to take for micro
        self.actions = []

    async def on_step(self, iteration):
        units = self.units()
        enemy = self.known_enemy_units()

        if self.training_loop < len(self.training_set):

            await self.do_micro()

            if not units or not enemy:
                self.record_result()

                # Clean up
                if units | enemy:
                    await self._client.debug_kill_unit(units | enemy)

                await self.spawn_iteration_units()
                self.iterate()

        else:

            if self.build_i == len(self.training_sets) - 1:
                if units | enemy:
                    # Cleanup remaining units
                    await self._client.debug_kill_unit(units | enemy)

                print("End of simulation. Results:")
                print("==========================")
                for record in self.combat_record:
                    print(record)

                sys.exit()

            else:
                # Next training set
                self.build_i += 1
                self.training_loop = 0
                self.training_set = self.training_sets[self.build_i]

    def iterate(self):
        print("TRAINING ITERATION: {} / {} of build {}".format(
            self.training_loop, len(self.training_set), self.build_i))

        self.training_loop += 1

    async def spawn_iteration_units(self):
        training_set = self.get_training_set()

        p1_units = training_set[0]
        p2_units = training_set[1]

        print("P1: {}".format(p1_units))
        print("P2: {}".format(p2_units))

        p1_position = self._game_info.map_center - sc2.position.Point2((-3, 0))
        p2_position = self._game_info.map_center - sc2.position.Point2((+3, 0))

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
        enemy = self.known_enemy_units()
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

    async def do_micro(self):
        await self.attack_enemy()
        await self.do_zergling_micro()

        # "Do" actions
        await self.do_actions(self.actions)

        # Reset actions
        self.actions = []

    async def attack_enemy(self):
        units = self.units.idle
        if units:
            enemy = self.known_enemy_units
            if enemy:
                for unit in units:
                    closest_enemy = enemy.closest_to(unit)
                    self.actions.append(unit.attack(closest_enemy.position))

    async def do_zergling_micro(self):
        """

        * Run away from nearby enemy banelings
        * If the nearest enemy is melee, then run away from them if my life is < 0.2

        """
        zerglings = self.units(const.ZERGLING)
        enemy = self.known_enemy_units

        if enemy:
            for zergling in zerglings:
                nearest_enemy = enemy.closest_to(zergling)
                if zergling.health_percentage < 0.1:
                    if nearest_enemy.distance_to(zergling) < 7 and \
                            nearest_enemy.can_attack_ground and \
                            nearest_enemy.ground_range < 1:
                        away_from_enemy = zergling.position.towards(nearest_enemy, -4)
                        self.actions.append(zergling.move(away_from_enemy))


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

        print("============================ Reloading Training Bot =================================")

        player_config[0].ai = TrainingBot()
        gen.send(player_config)


# Start game
if __name__ == '__main__':
    main()

