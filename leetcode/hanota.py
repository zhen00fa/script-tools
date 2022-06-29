class Solution:
    def hanota(self, A: list[int], B: list[int], C: list[int]) -> None:
        """
        Do not return anything, modify C in-place instead.
        """
        n = len(A)
        self.move(n, A, B, C)
        def move(self, n, A, B, C):
            if n == 1:
                C.append(A[-1])
                A.pop()
            else:
                self.move(n-1, )
class Solution:
    def hanota(self, A: list[int], B: list[int], C: list[int]) -> None:
        n = len(A)
        self.move(n, A, B, C)
    # 定义move 函数移动汉诺塔
    def move(self,n, A, B, C):
        if n == 1:
            C.append(A[-1])
            A.pop()
            return
        else:
            self.move(n-1, A, C, B)  # 将A上面n-1个通过C移到B
            C.append(A[-1])          # 将A最后一个移到C
            A.pop()                  # 这时，A空了
            self.move(n-1, B, A, C)   # 将B上面n-1个通过空的A移到C