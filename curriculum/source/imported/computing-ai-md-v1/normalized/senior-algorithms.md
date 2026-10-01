# 算法竞赛入门

## 第1章 程序设计入门

> **书名**：算法竞赛入门经典
> **作者**：刘汝佳
> **出版社**：清华大学出版社，2009（ISBN 9787302206088）
> **真实目录来源**：https://www.tup.com.cn/booksCenter/book_03224201.html
> **说明**：本文件基于该书真实章节结构整理高中段知识点，非逐字原文（受版权保护），原书代码为 C/C++，本讲义用 Python 重写以适配高中 Python 基础。细节与习题以原书为准。

全书 11 章：程序设计入门、循环结构、数组和字符串、函数和递归、基础题目选解、数据结构基础、暴力求解法、高效算法设计、动态规划初步、数学概念与方法、图论模型与算法。高中参加 CSP-J/S、NOIP 必看。

---

程序设计的本质是把一个问题拆成顺序执行的步骤。三个基本结构：顺序、分支、循环。

#### 算术表达式与变量

Python 中变量无需声明类型。注意整数除法 `/` 得浮点数，`//` 整除，`%` 取模，`**` 幂。

```python
a, b = 7, 3
print(a + b, a - b, a * b, a / b, a // b, a % b, a ** b)
```

输入输出：`input()` 读一行字符串，需 `int()`/`float()` 转换。竞赛中多组数据用 `sys.stdin` 加速。

```python
import sys
def main():
    data = sys.stdin.read().split()
    i = 0
    while i < len(data):
        a = int(data[i]); b = int(data[i+1])
        print(a + b)
        i += 2
main()
```

#### 分支结构

```python
score = int(input())
if score >= 90:
    print('A')
elif score >= 80:
    print('B')
else:
    print('C')
```

**常见误区**：浮点数相等判断。`0.1 + 0.2 == 0.3` 在 Python 里是 False（浮点精度）。比较浮点数用 `abs(a-b) < 1e-9`。

---

## 第2章 循环结构程序设计

#### for 循环与范围

```python
s = 0
for i in range(1, 101):
    s += i
print(s)
```

嵌套循环：

```python
for i in range(1, 10):
    for j in range(1, i+1):
        print(f'{j}*{i}={i*j}', end='\t')
    print()
```

#### 浮点数陷阱与 64 位整数

Python 整数任意精度，不用怕溢出；但浮点有精度。循环中累加浮点数会有误差，必要时用 `decimal` 模块。

#### 文件操作

竞赛中常用重定向 `python program.py < input.txt > output.txt`，或在代码里 `open()`。

---

## 第3章 数组和字符串

#### 数组

Python list 就是动态数组。多维数组用列表推导：

```python
matrix = [[0]*4 for _ in range(3)]
matrix[1][2] = 5
print(matrix)
```

#### 字符与字符串

字符用 `ord()`/`chr()` 转 ASCII。字符串不可变，拼接用 `''.join(list)`。

```python
s = 'hello'
print(ord('a'), chr(97))
rev = s[::-1]
print(rev)
```

#### 最长回文子串（中心扩展法）

```python
def longest_palindrome(s):
    n = len(s)
    if n < 2:
        return s
    start, max_len = 0, 1
    for i in range(n):
        for L, R in ((i-1, i+1), (i, i+1)):
            while L >= 0 and R < n and s[L] == s[R]:
                if R - L + 1 > max_len:
                    start, max_len = L, R - L + 1
                L -= 1; R += 1
    return s[start:start+max_len]

print(longest_palindrome('babad'))
```

复杂度 O(n²)。

---

## 第4章 函数和递归

#### 函数

函数封装可复用逻辑。Python 函数可返回多值（元组打包）。

#### 递归三要素

1. 基线条件（base case）：什么时候停止。
2. 递归条件：如何把问题缩小。
3. 返回值如何组合。

斐波那契：

```python
def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)
```

朴素递归 O(2ⁿ)，记忆化后 O(n)：

```python
from functools import lru_cache
@lru_cache
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)
```

汉诺塔：

```python
def hanoi(n, a, b, c):
    if n == 1:
        print(a, '->', c)
        return
    hanoi(n-1, a, c, b)
    print(a, '->', c)
    hanoi(n-1, b, a, c)

hanoi(3, 'A', 'B', 'C')
```

递归本质是栈：每次函数调用压栈，返回时弹栈。递归深度超过 `sys.setrecursionlimit(100000)` 会爆栈。

---

## 第5章 基础题目选解

### OJ 经典题 1：两数之和

给定 nums 和 target，返回两个下标使和为 target。

```python
def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            return [seen[target-x], i]
        seen[x] = i

print(two_sum([2,7,11,15], 9))
```

思路：用哈希表存已遍历值→下标，一次扫描 O(n)。暴力 O(n²)。

### OJ 经典题 2：斐波那契

```python
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a+b
    return a
```

迭代 O(n) O(1) 空间。

### OJ 经典题 3：走楼梯

每次走 1 或 2 阶，到 n 阶有几种走法？答案即斐波那契。`dp[i] = dp[i-1] + dp[i-2]`。

```python
def climb(n):
    if n <= 2:
        return n
    a, b = 1, 2
    for _ in range(3, n+1):
        a, b = b, a+b
    return b
```

---

## 第6章 数据结构基础

### 6.1 栈

栈是后进先出（LIFO）。Python list 当栈：`append`/`pop` O(1)。

括号匹配：

```python
def is_valid(s):
    pair = {')':'(', ']':'[', '}':'{'}
    st = []
    for ch in s:
        if ch in '([{':
            st.append(ch)
        else:
            if not st or st.pop() != pair[ch]:
                return False
    return not st

print(is_valid('({[]})'))
```

表达式求值（后缀/逆波兰）：

```python
def eval_rpn(tokens):
    st = []
    for t in tokens:
        if t in '+-*/':
            b = st.pop(); a = st.pop()
            if t == '+': st.append(a+b)
            elif t == '-': st.append(a-b)
            elif t == '*': st.append(a*b)
            else: st.append(int(a/b))
        else:
            st.append(int(t))
    return st[0]

print(eval_rpn(['2','1','+','3','*']))
```

### 6.2 队列与优先队列

队列先进先出（FIFO）。list.pop(0) 是 O(n)，用 `collections.deque` 是 O(1)。

```python
from collections import deque
q = deque()
q.append(1); q.append(2)
print(q.popleft())
```

优先队列用 `heapq`（最小堆）：

```python
import heapq
heap = []
heapq.heappush(heap, 3); heapq.heappush(heap, 1); heapq.heappush(heap, 2)
print(heapq.heappop(heap))
```

### 6.3 链表

```python
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class LinkedList:
    def __init__(self):
        self.head = None
    def push_front(self, val):
        self.head = ListNode(val, self.head)
    def push_back(self, val):
        if not self.head:
            self.head = ListNode(val); return
        p = self.head
        while p.next: p = p.next
        p.next = ListNode(val)
    def delete(self, target):
        dummy = ListNode(0, self.head)
        p = dummy
        while p.next:
            if p.next.val == target:
                p.next = p.next.next
                break
            p = p.next
        self.head = dummy.next
    def to_list(self):
        r = []
        p = self.head
        while p:
            r.append(p.val); p = p.next
        return r

ll = LinkedList()
ll.push_back(1); ll.push_back(2); ll.push_front(0)
ll.delete(1)
print(ll.to_list())
```

### 6.4 二叉树与遍历

```python
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def preorder(root):
    if not root: return []
    return [root.val] + preorder(root.left) + preorder(root.right)

def inorder(root):
    if not root: return []
    return inorder(root.left) + [root.val] + inorder(root.right)

def postorder(root):
    if not root: return []
    return postorder(root.left) + postorder(root.right) + [root.val]

from collections import deque
def levelorder(root):
    if not root: return []
    q = deque([root]); r = []
    while q:
        node = q.popleft()
        r.append(node.val)
        if node.left: q.append(node.left)
        if node.right: q.append(node.right)
    return r
```

二叉搜索树（BST）插入：

```python
def bst_insert(root, val):
    if not root:
        return TreeNode(val)
    if val < root.val:
        root.left = bst_insert(root.left, val)
    else:
        root.right = bst_insert(root.right, val)
    return root

def bst_search(root, val):
    if not root or root.val == val:
        return root
    if val < root.val:
        return bst_search(root.left, val)
    return bst_search(root.right, val)
```

### 6.5 堆与堆排序

```python
def heapify(arr, n, i):
    largest = i
    l, r = 2*i+1, 2*i+2
    if l < n and arr[l] > arr[largest]:
        largest = l
    if r < n and arr[r] > arr[largest]:
        largest = r
    if largest != i:
        arr[i], arr[largest] = arr[largest], arr[i]
        heapify(arr, n, largest)

def heap_sort(arr):
    a = arr[:]
    n = len(a)
    for i in range(n//2-1, -1, -1):
        heapify(a, n, i)
    for i in range(n-1, 0, -1):
        a[0], a[i] = a[i], a[0]
        heapify(a, i, 0)
    return a

print(heap_sort([3,1,4,1,5,9,2,6]))
```

### 6.6 并查集

```python
class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0]*n
    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb: return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True
```

路径压缩 + 按秩合并后近似 O(α(n))，α 是阿克曼反函数，增长极慢。

---

## 第7章 暴力求解法

枚举所有可能。DFS 回溯：

### 全排列

```python
def permute(nums):
    res = []
    def backtrack(path, used):
        if len(path) == len(nums):
            res.append(path[:])
            return
        for i in range(len(nums)):
            if used[i]: continue
            used[i] = True
            path.append(nums[i])
            backtrack(path, used)
            path.pop()
            used[i] = False
    backtrack([], [False]*len(nums))
    return res

print(permute([1,2,3]))
```

### 子集

```python
def subsets(nums):
    res = []
    def backtrack(start, path):
        res.append(path[:])
        for i in range(start, len(nums)):
            path.append(nums[i])
            backtrack(i+1, path)
            path.pop()
    backtrack(0, [])
    return res
```

### 八皇后

```python
def solve_n_queens(n):
    res = []
    def backtrack(row, cols, diag1, diag2, board):
        if row == n:
            res.append([''.join(r) for r in board])
            return
        for col in range(n):
            if col in cols or (row-col) in diag1 or (row+col) in diag2:
                continue
            board[row][col] = 'Q'
            backtrack(row+1, cols|{col}, diag1|{row-col}, diag2|{row+col}, board)
            board[row][col] = '.'
    backtrack(0, set(), set(), set(), [['.']*n for _ in range(n)])
    return res

print(len(solve_n_queens(8)))
```

---

## 第8章 高效算法设计

### 8.1 二分查找

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr)-1
    while lo <= hi:
        mid = (lo+hi)//2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid+1
        else:
            hi = mid-1
    return -1
```

O(log n)。

### 8.2 排序算法完整实现

```python
def bubble_sort(arr):
    a = arr[:]
    n = len(a)
    for i in range(n):
        for j in range(0, n-i-1):
            if a[j] > a[j+1]:
                a[j], a[j+1] = a[j+1], a[j]
    return a

def selection_sort(arr):
    a = arr[:]
    for i in range(len(a)):
        m = i
        for j in range(i+1, len(a)):
            if a[j] < a[m]: m = j
        a[i], a[m] = a[m], a[i]
    return a

def insertion_sort(arr):
    a = arr[:]
    for i in range(1, len(a)):
        key = a[i]
        j = i-1
        while j >= 0 and a[j] > key:
            a[j+1] = a[j]; j -= 1
        a[j+1] = key
    return a

def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr)//2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    r = []; i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            r.append(left[i]); i += 1
        else:
            r.append(right[j]); j += 1
    r.extend(left[i:]); r.extend(right[j:])
    return r

def quick_sort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr)//2]
    left = [x for x in arr if x < pivot]
    mid = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quick_sort(left) + mid + quick_sort(right)
```

**复杂度与稳定性对比**：

| 算法 | 最好 | 平均 | 最坏 | 空间 | 稳定 |
|------|------|------|------|------|------|
| 冒泡 | n | n² | n² | 1 | 是 |
| 选择 | n² | n² | n² | 1 | 否 |
| 插入 | n | n² | n² | 1 | 是 |
| 归并 | nlogn | nlogn | nlogn | n | 是 |
| 快排 | nlogn | nlogn | n² | logn | 否 |
| 堆排 | nlogn | nlogn | nlogn | 1 | 否 |

### 8.3 贪心

找零钱（贪心，币值为 1,5,10,20,100 时成立）：

```python
def greedy_change(coins, amount):
    coins.sort(reverse=True)
    count = 0
    for c in coins:
        count += amount // c
        amount %= c
    return count
```

活动选择（结束早优先）：

```python
def activity_selection(activities):
    activities.sort(key=lambda x: x[1])
    selected = [activities[0]]
    for a in activities[1:]:
        if a[0] >= selected[-1][1]:
            selected.append(a)
    return selected
```

---

## 第9章 动态规划初步

DP 四步：定义状态 → 转移方程 → 边界 → 遍历顺序。

### 0-1 背包

```python
def knapsack01(weights, values, W):
    n = len(weights)
    dp = [0]*(W+1)
    for i in range(n):
        for w in range(W, weights[i]-1, -1):
            dp[w] = max(dp[w], dp[w-weights[i]] + values[i])
    return dp[W]
```

### 完全背包

```python
def knapsack_complete(weights, values, W):
    n = len(weights)
    dp = [0]*(W+1)
    for i in range(n):
        for w in range(weights[i], W+1):
            dp[w] = max(dp[w], dp[w-weights[i]] + values[i])
    return dp[W]
```

### 最长公共子序列（LCS）

```python
def lcs(a, b):
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]
```

### 最长递增子序列（LIS）

```python
def lis(nums):
    tails = []
    for x in nums:
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo+hi)//2
            if tails[mid] < x: lo = mid+1
            else: hi = mid
        if lo == len(tails): tails.append(x)
        else: tails[lo] = x
    return len(tails)
```

### 编辑距离

```python
def edit_distance(a, b):
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m+1): dp[i][0] = i
    for j in range(n+1): dp[0][j] = j
    for i in range(1, m+1):
        for j in range(1, n+1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[m][n]
```

---

## 第10章 数学概念与方法

### 质数筛法

埃氏筛：

```python
def sieve(n):
    is_prime = [True]*(n+1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(n**0.5)+1):
        if is_prime[i]:
            for j in range(i*i, n+1, i):
                is_prime[j] = False
    return [i for i in range(2, n+1) if is_prime[i]]
```

欧拉筛（线性筛）：

```python
def euler_sieve(n):
    primes = []
    is_prime = [True]*(n+1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, n+1):
        if is_prime[i]:
            primes.append(i)
        for p in primes:
            if i*p > n: break
            is_prime[i*p] = False
            if i % p == 0: break
    return primes
```

### GCD / LCM

```python
def gcd(a, b):
    while b:
        a, b = b, a % b
    return a

def lcm(a, b):
    return a // gcd(a, b) * b
```

### 快速幂

```python
def qpow(a, b, mod):
    res = 1
    a %= mod
    while b:
        if b & 1:
            res = res * a % mod
        a = a * a % mod
        b >>= 1
    return res
```

### KMP 直觉

KMP 用前缀函数（pi 数组）避免重复匹配。pi[i] 是子串 s[0..i] 最长相等真前后缀长度。匹配失败时按 pi 回退，使总复杂度 O(n+m)。

---

## 第11章 图论模型与算法

### 邻接表建图

```python
from collections import deque

def bfs(graph, start, n):
    visited = [False]*n
    q = deque([start])
    visited[start] = True
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in graph[u]:
            if not visited[v]:
                visited[v] = True
                q.append(v)
    return order

def dfs(graph, start):
    visited = set()
    order = []
    def dfs_visit(u):
        visited.add(u); order.append(u)
        for v in graph[u]:
            if v not in visited:
                dfs_visit(v)
    dfs_visit(start)
    return order
```

### Dijkstra 最短路

```python
import heapq
def dijkstra(graph, n, start):
    dist = [float('inf')]*n
    dist[start] = 0
    pq = [(0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]: continue
        for v, w in graph[u]:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                heapq.heappush(pq, (dist[v], v))
    return dist
```

---

## CSP-J/S 衔接建议

CSP-J（入门级）与 CSP-S（提高级）每年 9-10 月举行，是 NOIP 的前置认证。J 组考枚举、模拟、递归、简单 DP、基础数据结构；S 组在此基础上加图论、数论、高级 DP、字符串。建议高一先用本书过 J 组知识点，高二冲 S 组，高三视情况打 NOIP/省选。

---

## 练习清单

1. 实现冒泡/选择/插入/归并/快排各一遍，对拍验证。
2. 用并查集做 Kruskal 最小生成树。
3. 用 DFS 判图是否有环。
4. 写 LCS 并输出具体子序列。
5. 把 0-1 背包改成二维 dp 再优化到一维。
