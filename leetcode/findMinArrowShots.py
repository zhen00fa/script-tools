class Solution:
    def findMinArrowShots(self, points: list[list[int]]) -> int:
        """
        :param points: points = [[10,16],[2,8],[1,6],[7,12]]
        :return: int 2
        """
        if not points:
            return 0
        points.sort(key=lambda balloon: balloon[1])
        pos = points[0][1]
        arrows = 1
        for point in points:
            if pos < point[0]:
                pos = point[1]
                arrows += 1
        return arrows

