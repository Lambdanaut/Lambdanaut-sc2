from collections import deque

class UnitCached(object):
    health_percentage = 0.001
    shield_percentage = 0.001

    is_taking_damage = False

    # Tracks last 10 positions of unit
    last_positions_maxlen = 10
    last_positions = None

    def __init__(self):
        # Initialize mutable variables
        self.last_positions = deque(maxlen=self.last_positions_maxlen)
