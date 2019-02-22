from functools import reduce
import random
from typing import List, Union

import lib.sc2.constants as const
from lib.sc2.unit import Unit
from lib.sc2.units import Units
from lib.sc2.position import Point2, Point3

import lambdanaut.const2 as const2


class Cluster(list):
    def __init__(self, position: Point2, *args: Union[Units, List[Unit]]):

        super(Cluster, self).__init__(*args)

        # 3D point where:
        # `x` is the x position in 2D sc2 space
        # `y` is the y position in 2D sc2 space
        # `z` is a special value used to break apart unit groups by unit type
        self._position: Point3 = position.to3

    @property
    def position(self):
        return self._position.to2

    @property
    def radius(self):
        """
        Returns the distance to the furthest unit within the cluster from
        the cluster's center
        """
        if self:
            return self.position.distance_to_furthest(self)
        else:
            return 0

    @property
    def center(self):
        return self.position

    def update_position(self) -> bool:
        """Updates the position by averaging the data in this cluster

        :returns A Boolean indicating if the position has changed
        """

        if not len(self):
            return False

        prev_position = self._position

        # Iterate over self, adding up all the points in ourself
        sum_of_self = reduce(
            lambda p1, p2: p1 + p2.position + self.unit_z_value(p2),
            self, Point3((0, 0, 0)))

        new_position = sum_of_self / len(self)

        position_changed = prev_position != new_position

        # Update position with new position
        self._position = new_position

        return position_changed

    def refresh(self):
        """
        Clears a cluster and sets its center to a random point of its data
        """
        if len(self):
            # Choose a random data point from self
            centroid = random.choice(self).position.to3
        else:
            # If we have no data, set a random point as the centroid
            centroid = Point3((random.randint(0, 300), random.randint(0, 300), random.randint(0, 15)))

        self.clear()
        self._position = centroid.position

    def merge(self, cluster2):
        """
        Merges the two clusters together and updates its position
        `cluster2` will be cleared and refreshed
        """
        self += cluster2
        self.update_position()
        cluster2.refresh()

    def unit_z_value(self, unit: Unit) -> Point3:
        """

        """
        unit_type = unit.type_id

        if unit.is_structure:
            return Point3((0, 0, 15))
        elif unit_type in const2.WORKERS:
            return Point3((0, 0, 10))

        else:
            return Point3((0, 0, 0))

    def __or__(self, other):
        """
        Adds two clusters together with the `|` operator

        :param other:  Another cluster to sum with this one
        :return:
        """
        new_cluster = Cluster((self.position + other.position) / 2, self + other)
        new_cluster.update_position()
        return new_cluster


def get_fresh_clusters(data, n=4) -> List[Cluster]:
    """
    Returns `n` fresh clusters that have not been calibrated
    """

    if len(data) < n:
        # If data is shorter than n, just create a list of linear points
        centroids = [Point2((i, i)) for i in range(0, 400, 400 // n)]

    else:
        # Otherwise choose n random data points from data to be our centers
        centroids = random.sample(data, n)

    return [Cluster(centroid.position, data) for centroid in centroids]


def k_means_update(clusters: List[Cluster], data):
    """
    Given clusters and data, mutably update the cluster's positions based on
    the data positions

    :param clusters: Clusters to update with new data
    :param data: Units or points to cluster on
    """

    for cluster in clusters:
        cluster.refresh()

    while True:

        for cluster in clusters:
            cluster.clear()

        for d in data:
            closest = d.position.closest(clusters)
            closest.append(d)

        if not any([cluster.update_position() for cluster in clusters]):
            break

    # Merge clusters that are very close to each other
    for cluster in clusters:
        clusters_excluding_this_cluster = [c for c in clusters if c.position != cluster.position]
        nearest_cluster = cluster.position.closest(clusters_excluding_this_cluster)

        if cluster and nearest_cluster and \
                cluster.position.distance_to(nearest_cluster.position) < 9:
            cluster.merge(nearest_cluster)
