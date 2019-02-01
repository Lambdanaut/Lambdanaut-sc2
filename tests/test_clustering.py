import sys, os
sys.path.append(os.path.realpath(os.path.dirname(__file__)+"/.."))

import functools
import unittest
import random

from sc2.position import Point2

import lambdanaut.clustering as clustering


class TestClustering(unittest.TestCase):
    def get_random_points(self):
        points1 = [Point2((random.randint(0, 10), random.randint(0, 10))) for i in range(20)]
        points2 = [Point2((random.randint(30, 50), random.randint(30, 50))) for i in range(20)]
        points3 = [Point2((random.randint(55, 80), random.randint(55, 80))) for i in range(20)]
        points4 = [Point2((random.randint(85, 90), random.randint(85, 90))) for i in range(20)]
        points5 = [Point2((random.randint(100, 200), random.randint(100, 200))) for i in range(20)]

        points = []
        points += points1 + points2 + points3 + points4 + points5

        return points

    def test_init(self):
        p1, p2, p3 = Point2((-5, -5)), Point2((0,0)), Point2((5,5))

        points = [p1, p2, p3]

        cluster = clustering.Cluster(p2, points)

        self.assertIn(p1, cluster)
        self.assertIn(p2, cluster)
        self.assertIn(p3, cluster)
        self.assertEqual(cluster.position, p2)

    def test_k_means(self):
        points = self.get_random_points()

        clusters = clustering.get_fresh_clusters(points, n=5)

        clustering.k_means_update(clusters, points)

        self.assertEqual(len(clusters), 5)

        for cluster in clusters:
            average_of_cluster = functools.reduce(lambda x, y: x + y, cluster) / len(cluster)
            self.assertEqual(cluster.position, average_of_cluster)

        points = self.get_random_points()

        clustering.k_means_update(clusters, points)

        self.assertEqual(len(clusters), 5)
        import pdb; pdb.set_trace()


if __name__ == '__main__':
    unittest.main()


