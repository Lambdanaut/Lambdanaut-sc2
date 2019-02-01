from functools import reduce
import random
from typing import List, Union

from sc2.units import Units
from sc2.position import Point2


class Cluster(list):
    def __init__(self, position: Point2, *args: Union["Units", List["Point2"]]):
        """

        :param position:
        :param args:
        """
        super(Cluster, self).__init__(*args)

        self.position = position

    def update_position(self) -> bool:
        """Updates the position by averaging the data in this cluster

        :returns A Boolean indicating if the position has changed
        """

        if not len(self):
            return False

        prev_position = self.position

        # Iterate over self, adding up all the points in ourself
        sum_of_self = reduce(lambda p1, p2: p1.position + p2.position, self, Point2((0, 0)))

        new_position = sum_of_self / len(self)

        position_changed = prev_position != new_position

        # Update position with new position
        self.position = new_position

        return position_changed


def get_fresh_clusters(data, n=4) -> Cluster:
    """
    Returns `n` fresh clusters that have not been calibrated
    """

    if len(data) < n:
        # If data is shorter than n, just create a list of linear points
        centroids = [Point2((i, i)) for i in range(n)]

    else:
        # Otherwise choose n random data points from data to be our centers
        centroids = random.sample(data, n)

    return [Cluster(centroid, data) for centroid in centroids]


def k_means_update(clusters: List[Cluster], data):
    """
    Given clusters and data, mutably update the cluster's positions based on
    the data positions

    :param clusters: Clusters to update with new data
    :param data: Units or points to cluster on
    """
    while True:

        for cluster in clusters:
            cluster.clear()

        for d in data:
            closest = d.position.closest(clusters)
            closest.append(d)

        if not any([cluster.update_position() for cluster in clusters]):
            break
