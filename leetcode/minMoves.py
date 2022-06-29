class Solution:
    def minMoves(self, nums: list[int]) -> int:
        """
        :param nums: [1,2,3]
        :return: 3
        """
        if len(nums) == 1:
            return 0
        a = len(nums) - 1
        b = max(nums)
        while True:
            count = sum(list(map(lambda x: b-x, nums))) // a
            if sum(list(map(lambda x: b-x, nums))) % a != 0:
                b += 1
            else:
                return count

