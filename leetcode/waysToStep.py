class Solution:
    def waysToStep(self, n: int) -> int:
        # f(n) = f(n-1)+f(n-2)+f(n-3) (n>3)
        a, b, c = 4, 2, 1
        if n < 3:
            return n
        if n == 3:
            return 4
        for i in range(n-3):
            a, b, c = (a+b+c) % 1000000007, a, b
        return a


        # 三步问题。有个小孩正在上楼梯，楼梯有n阶台阶，小孩一次可以上1阶、2阶或3阶。实现一种方法，计算小孩有多少种上楼梯的方式。结果可能很大，你需要对结果模1000000007
