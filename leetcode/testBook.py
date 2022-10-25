# import collections
#
# # Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, x):
#         self.val = x
#         self.left = None
#         self.right = None
#
# # 方法一
# class Solution:
#     def levelOrder(self, root: TreeNode):
#         if not root:
#             return []
#         nodes = []
#         cur_lay = [root]
#         while cur_lay:
#             next_lay = []
#             for i in cur_lay:
#                 if i.left:
#                     next_lay.append(i.left)
#                 if i.right:
#                     next_lay.append(i.right)
#                 nodes.append(i.val)
#             cur_lay = next_lay
#         return nodes
#
# # 方法二
# class Solution:
#     def levelOrder(self, root: TreeNode):
#         if not root: return []
#         res, queue = [], collections.deque()
#         queue.append(root)
#         while queue:
#             node = queue.popleft()
#             res.append(node.val)
#             if node.left: queue.append(node.left)
#             if node.right: queue.append(node.right)
#         return res
#
#
# # 输入一个整数数组，判断该数组是不是某二叉搜索树的后序遍历结果。如果是则返回 true，否则返回 false。假设输入的数组的任意两个数字都互不相同。
# # #
# # #  
# # #
# # # 参考以下这颗二叉搜索树：
# # #
# # #      5
# # #     / \
# # #    2   6
# # #   / \
# # #  1   3
# # # 示例 1：
# # #
# # # 输入: [1,6,3,2,5]
# # # 输出: false
# # # 示例 2：
# # #
# # # 输入: [1,3,2,6,5]
# # # 输出: true
# # 二叉搜索树定义： 左子树中所有节点的值 << 根节点的值；右子树中所有节点的值 >> 根节点的值；其左、右子树也分别为二叉搜索树。
#
# # [1, 2, 3, 4, 5]
# class Solution:
#     def verifyPostorder(self, postorder: list[int]) -> bool:
#         if not postorder:
#             return False
#         index = 0
#         for i in range(len(postorder)):
#             if postorder[i] > postorder[-1]:
#                 index = i
#                 break
#         for j in range(i, len(postorder)-1):
#             if postorder[j] < postorder[-1]:
#                 return False
#         left = True
#         right = True
#         if len(postorder[:index]) > 0:
#             left = self.verifyPostorder(postorder[:index])
#         if len(postorder[index:len(postorder)-1]) > 0:
#             right = self.verifyPostorder(postorder[index:len(postorder)-1])
#         return left and right
#
#
# # 二叉树中和为某一值的路径
# #
# # 给你二叉树的根节点 root 和一个整数目标和 targetSum ，找出所有 从根节点到叶子节点 路径总和等于给定目标和的路径。
# #
# # 叶子节点 是指没有子节点的节点。
# #
# #  
# # 示例 1：
# # 输入：root = [5,4,8,11,null,13,4,7,2,null,null,5,1], targetSum = 22
# # 输出：[[5,4,11,2],[5,8,4,5]]
# #
# # 示例 2：
# # 输入：root = [1,2,3], targetSum = 5
# # 输出：[]
# #
# # 示例 3：
# # 输入：root = [1,2], targetSum = 0
# # 输出：[]
# #  
# #
# # 提示：
# #
# # 树中节点总数在范围 [0, 5000] 内
# # -1000 <= Node.val <= 1000
# # -1000 <= targetSum <= 1000
#
#
# # Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
#
#
# class Solution:
#     def pathSum(self, root: TreeNode, target: int) -> list[list[int]]:
#         if not root:
#             return []
#         if not root.left and not root.right and root.val == target:
#             return [[root.val]]
#         res = []
#         left = self.pathSum(root.left, target - root.val)
#         right = self.pathSum(root.right, target - root.val)
#         for i in left + right:
#             res.append([root.val]+i)
#         return res
#
#
#
#
#
#
# def dynamic_p() -> list:
#     items = [  									 # 物品项
#         {"name": "水", "weight": 3, "value": 10},
#         {"name": "书", "weight": 1, "value": 3},
#         {"name": "食物", "weight": 2, "value": 9},
#         {"name": "小刀", "weight": 3, "value": 4},
#         {"name": "衣物", "weight": 2, "value": 5},
#         {"name": "手机", "weight": 1, "value": 10}
#     ]
#     max_capacity = 6                             # 约束条件为 背包最大承重为6
#     dp = [[0] * (max_capacity + 1) for _ in range(len(items) + 1)]
#
#     for row in range(1, len(items) + 1):         # row 代表行
#         for col in range(1, max_capacity + 1):   # col 代表列
#             weight = items[row - 1]["weight"]    # 获取当前物品重量
#             value = items[row - 1]["value"]      # 获取当前物品价值
#             if weight > col:                     # 判断物品重量是否大于当前背包容量
#                 dp[row][col] = dp[row - 1][col]  # 大于直接取上一次最优结果 此时row-1代表上一行
#             else:
#                 # 使用内置函数max()，将上一次最优结果 与 当前物品价值+剩余空间可利用价值 做对比取最大值
#                 dp[row][col] = max(value + dp[row - 1][col - weight], dp[row - 1][col])
#     return dp
#
#
# dp = dynamic_p()
# for i in dp:                                     # 打印数组
#     print(i)
#
# print(dp[-1][-1])                                # 打印最优解的价值和


# nums = [6, 10, 9, 2, 3, 6, 10, 661, 66]，这个数组的最长递增子序列是 [2, 3, 6, 10, 66]，
# def length_lis(nums: list) -> int:
#     for i in range(nums):
#
#     pass




# 实现lur算法

import collections

# class LRU:
#     def __init__(self, capacity=128):
#         pass
#
#     def put(self):
#         pass
#
#     def travel(self):
#         pass


# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, x):
#         self.val = x
#         self.next = None


# 给你一个类：
#
# public class Foo {
#   public void first() { print("first"); }
#   public void second() { print("second"); }
#   public void third() { print("third"); }
# }
# 三个不同的线程 A、B、C 将会共用一个 Foo 实例。
#
# 线程 A 将会调用 first() 方法
# 线程 B 将会调用 second() 方法
# 线程 C 将会调用 third() 方法
# 请设计修改程序，以确保 second() 方法在 first() 方法之后被执行，third() 方法在 second() 方法之后被执行。
#
# 提示：
#
# 尽管输入中的数字似乎暗示了顺序，但是我们并不保证线程在操作系统中的调度顺序。
# 你看到的输入格式主要是为了确保测试的全面性。
#  
#
# 示例 1：
#
# 输入：nums = [1,2,3]
# 输出："firstsecondthird"
# 解释：
# 有三个线程会被异步启动。输入 [1,2,3] 表示线程 A 将会调用 first() 方法，线程 B 将会调用 second() 方法，线程 C 将会调用 third() 方法。正确的输出是 "firstsecondthird"。
# 示例 2：
#
# 输入：nums = [1,3,2]
# 输出："firstsecondthird"
# 解释：
# 输入 [1,3,2] 表示线程 A 将会调用 first() 方法，线程 B 将会调用 third() 方法，线程 C 将会调用 second() 方法。正确的输出是 "firstsecondthird"。
#  
#
# 提示：
# nums 是 [1, 2, 3] 的一组排列


class Foo:
    def __init__(self):
        pass

    def first(self, printFirst: 'Callable[[], None]') -> None:
        # printFirst() outputs "first". Do not change or remove this line.
        printFirst()

    def second(self, printSecond: 'Callable[[], None]') -> None:
        # printSecond() outputs "second". Do not change or remove this line.
        printSecond()

    def third(self, printThird: 'Callable[[], None]') -> None:
        # printThird() outputs "third". Do not change or remove this line.
        printThird()

# Condition 条件对象法

# threading模块里的Condition方法，后面五种的方法也都是调用这个模块和使用不同的方法了，方法就是启动wait_for来阻塞每个函数，
# 直到指示self.t为目标值的时候才释放线程，with是配合Condition方法常用的语法糖，主要是替代try语句的。


import threading


class Foo:
    def __init__(self):
        self.c = threading.Condition()
        self.t = 0

    def first(self, printFirst: 'Callable[[], None]') -> None:
        self.res(0, printFirst)

    def second(self, printSecond: 'Callable[[], None]') -> None:
        self.res(1, printSecond)

    def third(self, printThird: 'Callable[[], None]') -> None:
        self.res(2, printThird)

    def res(self, val: int, func: 'Callable[[], None]') -> None:
        with self.c:
            self.c.wait_for(lambda: val == self.t)  # 参数是函数对象，返回值是bool类型
            func()
            self.t += 1
            self.c.notify_all()


# Lock锁对象法：
# 在这题里面功能都是类似的，就是添加阻塞，然后释放线程，只是类初始化的时候不能包含有参数，所以要写一句acquire进行阻塞，
# 调用其他函数的时候按顺序release释放。


import threading

class Foo:
    def __init__(self):
        self.l1 = threading.Lock()
        self.l1.acquire()
        self.l2 = threading.Lock()
        self.l2.acquire()

    def first(self, printFirst: 'Callable[[], None]') -> None:
        printFirst()
        self.l1.release()

    def second(self, printSecond: 'Callable[[], None]') -> None:
        self.l1.acquire()
        printSecond()
        self.l2.release()

    def third(self, printThird: 'Callable[[], None]') -> None:
        self.l2.acquire()
        printThird()


# Semaphore信号量对象法

import threading

class Foo:
    def __init__(self):
        self.s1 = threading.Semaphore(0)
        self.s2 = threading.Semaphore(0)

    def first(self, printFirst: 'Callable[[], None]') -> None:
        printFirst()
        self.s1.release()

    def second(self, printSecond: 'Callable[[], None]') -> None:
        self.s1.acquire()
        printSecond()
        self.s2.release()

    def third(self, printThird: 'Callable[[], None]') -> None:
        self.s2.acquire()
        printThird()

# Event事件对象法

import threading

class Foo:
    def __init__(self):
        self.e1 = threading.Event()
        self.e2 = threading.Event()

    def first(self, printFirst: 'Callable[[], None]') -> None:
        printFirst()
        self.e1.set()

    def second(self, printSecond: 'Callable[[], None]') -> None:
        self.e1.wait()
        printSecond()
        self.e2.set()

    def third(self, printThird: 'Callable[[], None]') -> None:
        self.e2.wait()
        printThird()


# dict字典法（WA
class Foo:
    def __init__(self):
        self.d = {}

    def first(self, printFirst: 'Callable[[], None]') -> None:
        self.d[0] = printFirst
        self.res()

    def second(self, printSecond: 'Callable[[], None]') -> None:
        self.d[1] = printSecond
        self.res()

    def third(self, printThird: 'Callable[[], None]') -> None:
        self.d[2] = printThird
        self.res()

    def res(self) -> None:
        if len(self.d) == 3:
            self.d[0]()
            self.d[1]()
            self.d[2]()


class Solution:
    def cuttingRope(self, n: int) -> int:
        dp = [0] * (n + 1)
        j * (n - j)

        j * dp[n - j]
        dp = [0] * (n + 1)
        for i in range(2, n + 1):
            for j in range(i):
                dp[i] = max(dp[i], j * (i - j), j * dp[i - j])
        return dp[n]
