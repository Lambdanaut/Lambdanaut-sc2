import lib.sc2.constants as const

from lambdanaut.expiringlist import ExpiringList
import lambdanaut.const2 as const2
from lambdanaut.const2 import ForcesStates, Messages
from lambdanaut.managers import Manager


class IntelManager(Manager):
    """
    Class for reading incoming pubsub messages and making adjustments to the intel
    held in the bot class.

    This is the only class with permission to directly access and edit variables in
    the Lambdanaut class and other managers.
    """

    name = 'Intel Manager'

    def __init__(self, bot):
        super(IntelManager, self).__init__(bot)

        self.has_scouted_enemy_air_tech = False
        self.has_scouted_enemy_counter_with_roaches = False
        self.has_scouted_enemy_counter_midgame_broodlord_rush = False
        self.has_scouted_enemy_greater_force = ExpiringList()  # Will contain True or nothing

        self.subscribe(Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION)
        self.subscribe(Messages.ARMY_COULDNT_FIND_ENEMY_BASE)
        self.subscribe(Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE)
        self.subscribe(Messages.ARMY_FOUND_ENEMY_BASE)

    async def read_messages(self):
        for message, val in self.messages.items():

            # Enemy location not where it was expected
            lost_enemy_location_msgs = {
                Messages.OVERLORD_SCOUT_WRONG_ENEMY_START_LOCATION,
                Messages.ARMY_COULDNT_FIND_ENEMY_BASE}
            if message in lost_enemy_location_msgs:
                self.ack(message)

                # Mark the current enemy start location as invalid
                self.bot.not_enemy_start_locations.add(self.bot.enemy_start_location)

                # Get potential enemy start locations that we have not already tried
                enemy_start_locations = \
                    [loc for loc in
                     self.bot.enemy_start_locations if loc not in
                     self.bot.not_enemy_start_locations]

                try:
                    new_enemy_start_location = enemy_start_locations[0]
                except IndexError:
                    # This would indicate a bug where we were unable to find the enemy in any start location
                    self.print("Couldn't find enemy base in any start location")
                    continue

                self.bot.enemy_start_location = new_enemy_start_location

            # Found enemy location
            found_enemy_location_msgs = {
                Messages.OVERLORD_SCOUT_FOUND_ENEMY_BASE,
                Messages.ARMY_FOUND_ENEMY_BASE}
            if message in found_enemy_location_msgs:
                self.ack(message)

                point = val
                enemy_start_locations = [loc for loc in self.bot.enemy_start_locations
                                         if loc != self.bot.start_location]
                new_enemy_start_location = point.closest(enemy_start_locations)

                self.bot.enemy_start_location = new_enemy_start_location
                self.bot.update_shortest_path_to_enemy_start_location()

    def enemy_counter_with_midgame_broodlord_rush(self):
        """Checks the map to see if there are any visible units we should counter with a broodlord rush"""
        if not self.has_scouted_enemy_counter_midgame_broodlord_rush:

            factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            tank_count = len(self.bot.known_enemy_units.of_type(
                {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if factory_count > 2 or tank_count > 3:
                self.has_scouted_enemy_counter_midgame_broodlord_rush = True
                return True

        return False

    def enemy_counter_with_midgame_roach_spotted(self):
        """Checks the map to see if there are any visible units we should counter with roach/hydra"""
        if not self.has_scouted_enemy_counter_with_roaches:
            enemy_counter_with_roach_types = {
                const.ROACH, const.ROACHWARREN, const.HELLIONTANK, const.PLANETARYFORTRESS}

            enemy_counter_with_roach_units = self.bot.known_enemy_units.of_type(enemy_counter_with_roach_types)

            factory_count = len(self.bot.known_enemy_units.of_type(const.FACTORY))
            # reaper_count = len(self.bot.known_enemy_units.of_type(const.REAPER))
            tank_count = len(self.bot.known_enemy_units.of_type(
                {const.SIEGETANK, const.SIEGETANKSIEGED}))

            if enemy_counter_with_roach_units.exists \
                    or factory_count > 1 \
                    or tank_count > 1:
                self.has_scouted_enemy_counter_with_roaches = True
                return True

        return False

    def enemy_air_tech_scouted(self):
        """Checks the map to see if there are any visible enemy air tech"""
        if not self.has_scouted_enemy_air_tech:
            enemy_air_tech_types = {
                const.STARGATE, const.SPIRE, const.LIBERATOR, const.BATTLECRUISER, const.ORACLE,
                const.BANSHEE, const.SMBANSHEE, const.SMARMORYBANSHEE,
                const.PHOENIX, const.BROODLORD, const.DARKSHRINE, const.GHOSTACADEMY,
                const.GHOST, const.MUTALISK, const.LURKERDENMP, const.LURKERMP, const.ROACHBURROWED,
                const.STARPORTTECHLAB, const.DARKTEMPLAR, const.LURKER, const.LURKERDEN}

            enemy_air_tech_units = self.bot.known_enemy_units.of_type(enemy_air_tech_types)

            if enemy_air_tech_units.exists:
                self.has_scouted_enemy_air_tech = True
                return True

        return False

    def greater_enemy_force_scouted(self):
        if not self.has_scouted_enemy_greater_force.contains(
                True, self.bot.state.game_loop):

            relative_army_strength = self.bot.relative_army_strength(
                self.bot.unit_cache.values(), self.bot.enemy_cache.values(),
                ignore_workers=True)

            if relative_army_strength < -3:
                self.has_scouted_enemy_greater_force.add(
                    True, self.bot.state.game_loop, expiry=30)
                return True

            return False

    def enemy_moving_out_scouted(self):
        """
        Checks to see if enemy units are moving out towards us
        """
        enemy_units = self.bot.known_enemy_units
        exclude_nonarmy_types = const2.WORKERS | {const.OVERLORD, const.OVERSEER}
        enemy_units = enemy_units.exclude_type(exclude_nonarmy_types).not_structure.\
            closer_than(80, self.bot.enemy_start_location)

        closer_enemy_counts = 0
        if len(enemy_units) > 3:
            for enemy_unit in enemy_units:
                if self.bot.moving_closer_to(
                        unit=enemy_unit,
                        cache=self.bot.enemy_cache,
                        point=self.bot.start_location):
                    closer_enemy_counts += 1

            # At least 6 enemy units were spotted moving closer to us for 10 iterations
            # Also the force manager is not currently attacking or moving to attack
            if self.bot.force_manager.state not in {ForcesStates.ATTACKING, ForcesStates.MOVING_TO_ATTACK} and \
                    closer_enemy_counts > 5:
                return True

        return False

    async def assess_game(self):
        """
        Assess the game's state and send out applicable messages
        """

        if self.enemy_air_tech_scouted():
            self.publish(Messages.ENEMY_AIR_TECH_SCOUTED)
        if self.enemy_counter_with_midgame_roach_spotted():
            self.publish(Messages.ENEMY_COUNTER_WITH_ROACHES_SCOUTED)
        if self.enemy_counter_with_midgame_broodlord_rush():
            self.publish(Messages.ENEMY_COUNTER_WITH_RUSH_TO_MIDGAME_BROODLORD)
        if self.greater_enemy_force_scouted():
            self.publish(Messages.FOUND_ENEMY_GREATER_FORCE)
            if len(self.bot.townhalls.ready) < 3:
                self.publish(Messages.FOUND_ENEMY_EARLY_AGGRESSION)
        if self.enemy_moving_out_scouted():
            self.publish(Messages.ENEMY_MOVING_OUT_SCOUTED)

    async def run(self):
        await self.read_messages()
        await self.assess_game()


