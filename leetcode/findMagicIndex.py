class Solution:
    def findMagicIndex(self, nums: list[int]) -> int:
        # a = (i for i, num in enumerate(nums) if i == num)
        return next(iter(i for i, num in enumerate(nums) if i == num), -1)
    # 魔术索引。 在数组A[0...n-1]中，有所谓的魔术索引，满足条件A[i] = i。给定一个有序整数数组，
    # 编写一种方法找出魔术索引，若有的话，
    # 在数组A中找出一个魔术索引，如果没有，则返回-1。若有多个魔术索引，返回索引值最小的一个。