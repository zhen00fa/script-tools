class Solution:
    def getNoZeroIntegers(self, n: int):
        def checkzero(x):
            if '0' in str(x):
                return True
            else:
                return False
        for i in range(1, n//2 + 1):
            if not checkzero(i) and not checkzero(n-i):
                return [i, n-i]
