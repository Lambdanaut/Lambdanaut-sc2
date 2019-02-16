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

        prev_position = self.position

        # Iterate over self, adding up all the points in ourself
        sum_of_self = reduce(lambda p1, p2: p1.position + p2.position, self, Point2((0, 0)))

        new_position = sum_of_self / len(self)

        position_changed = prev_position != new_position

        # Update position with new position
        self.position = new_position

        return position_changed

    def refresh(self):
        """
        Clears a cluster and sets its center to a random point of its data
        """
        if len(self):
            # Choose a random data point from self
            centroid = random.choice(self)
        else:
            # If we have no data, set a random point as the centroid
            centroid = Point2((random.randint(0, 300), random.randint(0, 300)))

        self.clear()
        self.position = centroid.position

    def merge(self, cluster2):
        """
        Merges the two clusters together and updates its position
        `cluster2` will be cleared and refreshed
        """
        self += cluster2
        self.update_position()
        cluster2.refresh()


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
                cluster.position.distance_to(nearest_cluster.position) < 18:
            cluster.merge(nearest_cluster)
