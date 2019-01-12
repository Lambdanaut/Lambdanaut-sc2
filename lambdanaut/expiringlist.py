from lambdanaut.const2 import FPS


class ExpiringList(object):
    """
    List container that expires objects based on a given expiry and iteration time

    Example:
    >>> from lambdanaut.expiringlist import ExpiringList
    >>> x=ExpiringList()
    >>> x.add('farts', 0, 10)
    >>> x.add('darts', 5, 15)
    >>> x.l
    [('farts', 0, 10), ('darts', 5, 15)]
    >>> x.contains('farts', 2)
    True
    >>> x.contains('farts', 9)
    True
    >>> x.contains('farts', 10)
    True
    >>> x.contains('farts', 11)
    False
    >>> x.l;
    [('darts', 5, 15)]

    """

    def __init__(self, divide_by_fps=True):
        """

        :param divide_by_fps: Decides whether to multiple the passed-in expiry
               by the fps used in faster sc2 matches (22.5 fps)
        """
        self.l = []
        self.divide_by_fps = divide_by_fps

    def add(self, item, iteration, expiry):
        """Adds an item to the list with the given expiration"""
        to_append = (item, iteration, round(expiry * FPS))
        self.l.append(to_append)

    def contains(self, item, current_iteration):
        """Returns True if it's in the list and hasn't expired, otherwise returns False"""
        for i in range(len(self.l)):
            list_item, item_iteration, expiry = self.l[i]
            if item == list_item:
                if current_iteration - item_iteration > expiry:
                    # Expired. Delete it
                    self.l.pop(i)
                    return False
                else:
                    # Not expired. Return it
                    return True
        return False

    def items(self, current_iteration):
        """Cleans list of expired items and returns it"""
        to_pop = []

        for i in range(len(self.l)):
            list_item, item_iteration, expiry = self.l[i]
            if current_iteration - item_iteration > expiry:
                # Expired. Delete it
                to_pop.append(i)

        for i in to_pop:
            self.l.pop(i)

        return [item for item, iteration, expiry in self.l]

