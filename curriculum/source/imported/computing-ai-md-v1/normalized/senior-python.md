# Python 进阶

## 第1章 Python数据模型

> **书名**：流畅的Python（第2版）（Fluent Python, 2nd Edition）
> **作者**：Luciano Ramalho
> **出版社**：人民邮电出版社（上下两册）
> **真实目录来源**：https://www.ptpress.com.cn/publishing/book/8dc8205c-08fb-48cd-a11f-22ef520cb2fc
> **说明**：本文件基于该书真实章节结构整理高中段知识点，非逐字原文（受版权保护），细节与示例以原书为准。代码为教学重写，可直接运行。

本书面向已经掌握 Python 基础语法、想进一步写出"Python 风格"代码的高中生。全书 20 章分四部分：数据结构、函数即对象、类和协议、控制流。高中阶段重点掌握第 1、2、3、6、7、9、11、14、17、19 章。

---

## 第一部分 数据结构

Python 数据模型是一套由解释器约定的特殊方法协议。当你写 `len(x)`、`x[i]`、`for i in x`、`str(x)` 时，解释器底层分别调用 `x.__len__()`、`x.__getitem__(i)`、`iter(x)`、`x.__str__()`。这叫"鸭子类型"：不需要继承某个特定类，只要实现了这些特殊方法，你的对象就能融入 Python 的语法糖。

经典例子是一摞扑克牌。用 `__getitem__` 和 `__len__` 后，一副牌立刻支持索引、切片、迭代、`in` 运算，完全不需要额外代码。

```python
import collections

Card = collections.namedtuple('Card', ['rank', 'suit'])

class FrenchDeck:
    ranks = [str(n) for n in range(2, 11)] + list('JQKA')
    suits = 'spades diamonds clubs hearts'.split()

    def __init__(self):
        self._cards = [Card(r, s) for s in self.suits for r in self.ranks]

    def __len__(self):
        return len(self._cards)

    def __getitem__(self, position):
        return self._cards[position]

deck = FrenchDeck()
print(len(deck))
print(deck[0])
print(deck[-1])
for c in deck:
    pass
print(Card('Q', 'hearts') in deck)
```

为什么 `len(x)` 不是 `x.len()`？因为 Python 对内置类型做了优化：CPython 直接从对象头读长度字段，避免一次方法调用。特殊名字 `__len__` 让用户自定义类型也能走这条快路。

**常见误区**：把 `__repr__` 和 `__str__` 搞混。`__repr__` 是给开发者看的官方表示（在交互环境、调试器里显示），`__str__` 是给终端用户看的（`print` 时）。如果只实现一个，实现 `__repr__`，因为 `str()` 找不到时会回退到 `repr()`。

**练习**：给上面的 `FrenchDeck` 加 `__repr__`，让 `print(deck)` 输出可读内容。

---

## 第2章 丰富的序列

Python 序列分两类：容器序列（list、tuple、collections.deque，存任意类型引用）和扁平序列（str、bytes、array.array，存连续内存中的原始值）。可变序列（list、bytearray、array）和不可变序列（tuple、str、bytes）。

#### 列表推导式

列表推导式（listcomp）是构造列表最 Pythonic 的方式。它比 `map/filter` 更可读。

```python
symbols = '$¢£¥€¤'
beyond_ascii = [ord(s) for s in symbols if ord(s) > 127]
print(beyond_ascii)

colors = ['black', 'white']
sizes = ['S', 'M', 'L']
tshirts = [(c, s) for c in colors for s in sizes]
print(tshirts)
```

笛卡儿积用两层 for 即可。生成器表达式（genexp）用圆括号，逐个产出元素，不一次性建列表，适合大数据或喂给函数：

```python
tuple(ord(s) for s in symbols)
sum(ord(s) for s in symbols)
```

#### 元组不仅是不可变列表

元组有两个用途：作为记录（每个位置有固定含义）和作为不可变列表。

```python
lax_coordinates = (33.9425, -118.408056)
city, year, pop, chg, area = ('Tokyo', 2003, 32450, 0.66, 8014)
traveler_ids = [('USA', '31195855'), ('BRA', 'CE342567')]
for passport in sorted(traveler_ids):
    print('%s/%s' % passport)
for country, _ in traveler_ids:
    print(country)
```

元组拆包是核心技巧：平行赋值、`*` 捕获多余项、函数调用传 `*args`。

```python
a, b, *rest = range(5)
print(a, b, rest)
a, *body, c, d = range(5)
print(a, body, c, d)
```

#### 切片

`s[a:b:c]` 表示从 a 到 b 步长 c。负数步长倒序。切片区间"含头不含尾"是为了方便切分（`s[:x]` 和 `s[x:]` 拼接等于 `s`）。

```python
s = 'bicycle'
print(s[::3])
print(s[::-1])
print(s[::-2])
```

切片对象 `slice(None, 10, 2)` 可以复用。给切片赋值会就地修改原列表。

#### `+` 和 `*`

`[[]] * 3` 得到三个引用同一列表的元素——这是经典陷阱。要建嵌套列表用列表推导。

```python
board = [['_'] * 3 for _ in range(3)]
board[0][0] = 'X'
print(board)
```

`+=` 的谜题：`a += b` 对可变列表就地修改，但如果 `a` 是元组里的列表，元组本身不可变却能修改其中元素。`list.sort()` 就地排序返回 None，内置 `sorted()` 返回新列表——这是"就地还是新建"的设计惯例。

#### 当列表不适用时

需要纯数值数组用 `array.array`（紧凑 C 数组）；需要两端操作用 `collections.deque`（O(1) 头尾增删）；做科学计算直接用 NumPy。

**复杂度表**：

| 结构 | 索引 | 尾部追加 | 头部插入/删除 | 查找值 |
|------|------|----------|---------------|--------|
| list | O(1) | 均摊 O(1) | O(n) | O(n) |
| deque | O(n) | O(1) | O(1) | O(n) |
| array.array | O(1) | O(1) | O(n) | O(n) |

---

## 第3章 字典和集合

dict 是 Python 的核心。3.9+ 支持字典推导、合并 `|`、解包 `**`。

```python
d1 = {'a': 1, 'b': 2}
d2 = {'b': 3, 'c': 4}
print(d1 | d2)
merged = {**d1, **d2}
print(merged)
```

"可哈希"（hashable）：一个对象在生命周期内哈希值不变，且支持 `__eq__`。原子不可变类型（str、bytes、int、float、tuple）默认可哈希；tuple 只有所含元素都可哈希才可哈希。dict 的键必须可哈希。

`defaultdict` 自动处理缺失键：

```python
from collections import defaultdict
dd = defaultdict(list)
dd['a'].append(1)
dd['b'].append(2)
print(dd)
```

`dict.__missing__` 是另一种处理缺失键的机制。dict 变体：`OrderedDict`（保持插入顺序，Python 3.7+ 普通 dict 也保序了）、`ChainMap`（串联多个映射查）、`Counter`（计数）、`UserDict`（子类化用它而不是 dict）。

```python
from collections import Counter
ct = Counter('abracadabra')
print(ct.most_common(2))
```

set 是集合数学运算的实现：交并差。`set` 字面量 `{1,2,3}` 比 `set([1,2,3])` 快。空集合必须写 `set()`（`{}` 是空字典）。

dict/set 底层是散列表：平均 O(1) 查找，但最坏情况 O(n)（哈希碰撞）。这就是为什么键必须可哈希。Python 3.7+ dict 保持插入顺序，是 CPython 的实现细节被纳入语言规范。

**常见误区**：在遍历 dict 时增删键会报错或漏项。要遍历就先 `list(d.items())` 拷贝。

---

## 第4章 Unicode文本和字节序列

核心区分：`str` 是 Unicode 码点序列，`bytes` 是字节序列。文本读写必须显式指定编码。

```python
s = 'café'
b = s.encode('utf-8')
print(b)
print(b.decode('utf-8'))
```

编码错误处理：`encode` 时 `UnicodeEncodeError`，`decode` 时 `UnicodeDecodeError`。用 `errors='replace'` 容错，但生产环境宁可失败。

文本文件打开必须指定 `encoding='utf-8'`，否则用系统默认（Windows 上常是 gbk，Linux 上是 utf-8），跨平台必出 bug：

```python
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write('hello')
```

规范化：Unicode 有等价表示（`é` 可以是单码点 U+00E9，也可以是 e + 组合重音符 U+0301）。比较前用 `unicodedata.normalize('NFC', s)`。

---

## 第5章 数据类构建器

`collections.namedtuple` 和 `@dataclass` 用来构建轻量记录类。

```python
from collections import namedtuple
City = namedtuple('City', 'name country population coordinates')
tokyo = City('Tokyo', 'JP', 36.933, (35.689722, 139.691667))
print(tokyo.name)
```

```python
from dataclasses import dataclass, field

@dataclass
class ClubMember:
    name: str
    guests: list = field(default_factory=list)
    age: int = 0
```

`@dataclass` 自动生成 `__init__`、`__repr__`、`__eq__`。类型提示在运行时不强制（只是注解），由 mypy 等工具静态检查。`field(default_factory=list)` 避免"可变默认参数"陷阱。

---

## 第6章 对象引用、可变性和垃圾回收

Python 变量不是盒子，是标签。赋值 `b = a` 只是贴新标签到同一对象。

```python
a = [1, 2, 3]
b = a
b.append(4)
print(a)
```

`==` 比较值，`is` 比较身份（同一对象）。单例比较用 `is None` 而非 `== None`。

浅拷贝 vs 深拷贝：`list(lst)`、`lst[:]`、`copy.copy()` 都是浅拷贝——外层新列表，但元素还是引用。嵌套结构要 `copy.deepcopy()`。

**可变默认参数陷阱**：

```python
class HauntedBus:
    def __init__(self, passengers=[]):
        self.passengers = passengers
```

每次不传 passengers 都用同一个列表对象——这是 bug。改用 `None` 作默认值，在 `__init__` 里新建。

`del` 删除的是引用不是对象；对象被回收当引用计数归零。Python 用引用计数为主，辅以分代垃圾回收处理循环引用。

---

## 第二部分 函数即对象

## 第7章 函数是一等对象

在 Python 里函数是对象：可以赋值给变量、作参数传递、作返回值、放进列表字典。

```python
def factorial(n):
    return 1 if n < 2 else n * factorial(n-1)

f = factorial
print(f(5))
print(list(map(f, range(5))))
```

高阶函数：`map`、`filter`、`sorted(key=...)`、`functools.reduce`。现在更推荐列表推导替代 map/filter：

```python
list(map(factorial, range(6)))
[factorial(n) for n in range(6)]
list(map(factorial, filter(lambda n: n % 2, range(6))))
[factorial(n) for n in range(6) if n % 2]
```

`lambda` 只能是表达式，适合作一次性参数。9 种可调用对象包括：函数、内置函数、方法、类、实例（定义了 `__call__`）、生成器函数等。

参数机制：`*args` 收集多余位置参数，`**kwargs` 收集多余关键字参数。仅限关键字参数（keyword-only）在 `*` 之后声明：

```python
def f(a, *args, c, **kwargs):
    pass
```

`operator` 模块把运算符变成函数（`itemgetter(1)`、`attrgetter('age')`、`methodcaller`），`functools.partial` 冻结部分参数。

---

## 第8章 函数中的类型提示

类型提示（type hints）是可选注解，运行时不检查。mypy 等工具静态检查。

```python
def greet(name: str) -> str:
    return 'Hello, ' + name

def show_count(count: int, word: str, plural: str = '') -> str:
    if count == 1:
        return f'1 {word}'
    return f'{count} {plural or word + "s"}'
```

常用类型：`Optional[X]` 表示 X 或 None，`Union[X, Y]`，`List[int]`、`Dict[str, int]`、`Tuple[int, ...]`。高中阶段知道怎么读注解即可。

---

## 第9章 装饰器和闭包

装饰器是语法糖：`@deco` 等价于 `func = deco(func)`。装饰器在模块导入时立即执行。

```python
def decorate(func):
    def inner():
        print('before')
        func()
        print('after')
    return inner

@decorate
def say_hi():
    print('hi')

say_hi()
```

**闭包**：内层函数记住了外层函数的变量，即使外层已返回。

```python
def make_averager():
    series = []
    def averager(new_value):
        series.append(new_value)
        return sum(series) / len(series)
    return averager

avg = make_averager()
print(avg(10))
print(avg(11))
```

`nonlocal` 声明把变量标记为自由变量（用于不可变类型需要重新赋值时）。

标准库装饰器：`@functools.cache`（备忘/记忆化）、`@lru_cache`、`@functools.wraps`（保留原函数元数据）。

```python
from functools import lru_cache

@lru_cache
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)
```

参数化装饰器需要三层嵌套。**练习**：写一个计时装饰器 `@clock`，打印函数运行时间。

---

## 第10章 使用一等函数实现设计模式

策略模式：经典 OOP 是定义抽象策略类再写子类；Python 里函数是对象，直接传不同函数即可。命令模式同理，把函数当作命令对象。

---

## 第三部分 类和协议

## 第11章 符合Python风格的对象

实现 `__repr__`、`__eq__`、`__hash__`、`__slots__`。

`@classmethod` 定义备选构造函数（常用 `frombytes` 等），`@staticmethod` 是普通函数放在类命名空间。

`__slots__`：在类里声明 `__slots__ = ('x', 'y')`，实例不再有 `__dict__`，省内存（大量实例时显著），但不能动态加属性、不能多继承。

```python
class Vector2d:
    __slots__ = ('__x', '__y')
    def __init__(self, x, y):
        self.__x = x
        self.__y = y
```

私有属性约定：单前缀下划线 `_x` 是"受保护"提示，双前缀 `__x` 触发名称改写（`_Class__x`），不是真私有。

---

## 第12章 序列的特殊方法

实现 `__getitem__`、`__len__` 让类成为序列。切片支持靠 `__getitem__` 接收 `slice` 对象。

---

## 第13章 接口、协议和抽象基类

鸭子类型：不关心对象是什么类，只关心它能不能用（`len()` 能不能调）。抽象基类（ABC）用 `abc.ABCMeta` + `@abstractmethod` 定义正式接口。`collections.abc` 提供 Iterable、Sized、Sequence、MutableMapping 等。

---

## 第14章 继承：瑕瑜互见

`super()` 委托父类方法。多重继承用 MRO（方法解析顺序，C3 线性化）查找。混入类（mixin）是专门被多继承复用的小类，不单独实例化。

```python
class A:
    def hello(self):
        print('A')

class B(A):
    def hello(self):
        print('B')
        super().hello()

class C(A):
    def hello(self):
        print('C')
        super().hello()

class D(B, C):
    def hello(self):
        print('D')
        super().hello()

print([c.__name__ for c in D.__mro__])
D().hello()
```

**原则**：优先用组合而非继承；只子类化专门设计来被继承的类；避免多重继承复杂层级。

---

## 第15-16章 类型提示进阶与运算符重载

运算符重载实现 `__add__`、`__mul__`、`__lt__` 等特殊方法，让自定义对象支持 `+`、`*`、`<`。

```python
class Vector:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)
    def __repr__(self):
        return f'Vector({self.x}, {self.y})'
```

---

## 第四部分 控制流

## 第17章 迭代器、生成器和经典协程

可迭代对象（iterable）实现了 `__iter__`；迭代器（iterator）实现了 `__next__` 和 `__iter__`。`iter(x)` 从可迭代对象拿迭代器，`next(it)` 取下一个，抛 `StopIteration` 结束。

生成器函数用 `yield`：

```python
def gen_range(n):
    i = 0
    while i < n:
        yield i
        i += 1

for x in gen_range(5):
    print(x)
```

生成器是惰性的：每次 `next` 才计算下一个值，不一次性占内存。标准库 `itertools` 提供 `chain`、`count`、`cycle`、`islice`、`product`、`combinations`、`permutations` 等。

`yield from` 把子生成器的元素逐个产出：

```python
def chain(*iters):
    for it in iters:
        yield from it
```

---

## 第18章 with、match和else块

`with` 上下文管理器：`__enter__` 和 `__exit__` 保证资源释放（文件、锁、连接）。

```python
with open('a.txt', 'w', encoding='utf-8') as f:
    f.write('hello')
```

`@contextlib.contextmanager` 用生成器实现上下文管理器。`try/except/else`：`else` 块在没有异常时执行。`match/case` 是 Python 3.10+ 的结构模式匹配。

---

## 第19章 Python并发模型

三种并发：线程（threading）、进程（multiprocessing）、协程（asyncio）。

**GIL（全局解释器锁）**：CPython 同一时刻只有一个线程执行 Python 字节码。CPU 密集型多线程无法利用多核，要多进程；I/O 密集型（网络、文件）多线程或协程即可。

```python
import threading
def worker(n):
    print(f'worker {n}')

threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
for t in threads: t.start()
for t in threads: t.join()
```

---

## 第20章 并发执行器

`concurrent.futures.ThreadPoolExecutor` / `ProcessPoolExecutor` 封装了线程/进程池：

```python
from concurrent.futures import ThreadPoolExecutor
import time

def download(url):
    time.sleep(1)
    return url

urls = ['a', 'b', 'c']
with ThreadPoolExecutor(max_workers=3) as ex:
    results = list(ex.map(download, urls))
print(results)
```

`as_completed` 哪个先完成先处理。高中阶段理解"并发 vs 并行"、GIL 影响即可。

---

## 高中阶段重点练习建议

1. 用 `@dataclass` 重写一个学生成绩记录类，支持排序和统计。
2. 写一个 `@lru_cache` 装饰的斐波那契函数，对比递归版和记忆化版性能。
3. 实现一个可迭代的 `Range` 类（自己的 range）。
4. 用 `ThreadPoolExecutor` 并发下载多个网页 URL。
5. 用 `__slots__` 写一个 100 万元素的点类，观察内存差异。
