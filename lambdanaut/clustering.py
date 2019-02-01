from functools import reduce
import random
from typing import List

from sc2.position import Point2


class Cluster(list):
    def __init__(self, position: Point2, *args):
        super(Cluster, self).__init__(*args)

        self.position = position

    def update_position(self) -> bool:
        """Updates the position by averaging the data in this cluster

        :returns A Boolean indicating if the position has changed
        """

        if len(self) == 0:
            return False

        prev_position = self.position
        sum_of_self = reduce(lambda x, y: x+y, self)
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


def k_means_update(clusters: List[Cluster], data) -> List[Cluster]:
    """
    Given clusters and data, update the cluster's positions based on the data positions

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
