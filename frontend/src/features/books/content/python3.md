> 本书由霜铃 K12 教学助手编写，示例为原创练习。内容按 Python 官方教程的主题体系整理，代码面向 Python 3.12 及以上版本。阅读时请亲自运行代码：能预测输出、解释原因、修改输入，是比背语法更可靠的掌握标准。

## 第1章 从解释器到第一个程序

Python 程序可以在交互式解释器里一行行运行，也可以保存成 `.py` 文件后重复执行。交互模式适合试算和探索；脚本适合保存、分享与构建稍大的程序。两种方式使用同一门语言，差别在于代码的保存和运行方式。

先在终端检查安装：

```bash
python3 --version
```

Windows 上也可以使用 `py --version`。版本号至少应为 3.12。本书使用的基本语法在 Python 3 的多个版本中都适用。

新建 `hello.py`：

```python
name = "小林"
print(f"你好，{name}！")
```

在终端进入文件所在目录并运行 `python3 hello.py`。`print` 把值显示出来；变量 `name` 保存文本；前缀为 `f` 的字符串会把花括号中的表达式计算后放入文本。

运行程序时，解释器会读取源代码、检查语法，再按顺序执行语句。若缩进不正确，程序可能报 `IndentationError`；若名字不存在，可能报 `NameError`。错误信息通常会指出文件、行号和错误类别。先找到最后几行的错误，再检查对应代码，不要一看到报错就重写整个程序。

**练习**：让程序分别输出你的名字、今天想学的主题和一条鼓励自己的话；再把三条输出改成一条 f-string。

## 第2章 值、变量与类型

程序操作的是值。`42` 是整数，`3.5` 是浮点数，`"Python"` 是字符串，`True` 和 `False` 是布尔值。变量名让程序可以再次引用一个值：

```python
score = 86
student = "小林"
passed = score >= 60
print(student, passed)
```

等号 `=` 表示赋值，意思是把右侧表达式算出的对象绑定到左侧名字。比较是否相等要使用 `==`。变量不需要先声明类型，但每个值都有类型；`type(score)` 可以帮助观察类型。动态类型让尝试更快，也要求程序员明确输入、转换和边界。

类型影响运算规则。`"3" + "4"` 会拼接成 `"34"`，而 `3 + 4` 得到 `7`。用户输入通常是文本：

```python
age_text = input("请输入年龄：")
age = int(age_text)
print(f"明年你将满 {age + 1} 岁")
```

如果输入 `小林`，`int` 会抛出 `ValueError`；不是所有字符串都能转换成整数。把转换放进异常处理，或先验证输入，才能给用户清楚的提示。

命名应表达用途，例如 `total_score` 比 `x` 更容易读。常量通常用全大写名字表达约定，例如 `PASSING_SCORE = 60`；Python 不会强制它不可修改。名字不能以数字开头，也不能使用 `if`、`for` 这类关键字。不要用 `list`、`str`、`sum` 覆盖内置名称，否则会让后续代码变得难以理解。

**练习**：读入商品单价和数量，转换为数值并计算总价。思考：输入为空、输入文字或数量为零时，程序应怎样回应？

## 第3章 数字、字符串与格式化

整数适合计数，浮点数适合近似表示小数。`/` 总是产生浮点数；`//` 做向下取整的整除；`%` 取余数；`**` 求幂。处理金额时，不要假设二进制浮点数能精确表示所有十进制小数：`0.1 + 0.2` 的结果可能显示成非常接近 `0.3`、但不完全相等的值。涉及货币或精确小数时，使用 `decimal.Decimal` 并从文本构造。

字符串是不可变的 Unicode 文本。不可变意味着不能原地改掉某个字符，修改通常会产生新字符串。下标从 `0` 开始，切片的结束位置不包含在结果里：

```python
word = "python"
print(word[0])       # p
print(word[1:4])    # yth
print(word[-1])     # n
print(word[:2])     # py
```

切片越界通常不会报错，而是返回可用部分；直接访问不存在的下标则会 `IndexError`。常用方法包括 `strip()` 去除两端空白、`lower()` 转小写、`split()` 按分隔符切分、`join()` 把字符串序列连接起来。字符串方法不会修改原字符串。

给人看的输出优先用 f-string：

```python
price = 12.5
count = 3
print(f"单价：{price:.2f} 元；数量：{count} 件；小计：{price * count:.2f} 元")
```

格式说明 `:.2f` 把数字显示为两位小数。格式化只改变显示，不会把底层数值变成货币类型。对来自用户的文本，输出到网页、SQL 或 shell 命令时还要按照目标环境进行安全处理；字符串插值不是通用的安全转义机制。

**练习**：输入一句话，分别显示去掉首尾空白后的文本、字符数和用空格分开的单词数。测试空字符串和只有空格的输入。

## 第4章 列表、元组、集合与字典

选数据结构前先问：要不要按顺序保存？需不需要修改？要不要按键快速查找？

列表保存有序、可修改的元素：

```python
scores = [86, 92, 74]
scores.append(88)
scores[0] = 90
print(scores)
```

`append` 修改原列表并返回 `None`，所以不要写 `scores = scores.append(88)`。`sort()` 也会原地排序；若想得到新列表可用 `sorted(scores)`。列表可以包含不同类型，但真实项目里尽量让同一列表表达一种清晰的数据概念。

元组用圆括号，通常表示一组不打算改变的固定字段，例如坐标 `(3, 5)`。元组只有一个元素时要写逗号：`("Python",)`。元组不可修改，但若其中装着可变对象，那些对象本身仍可能变化。

集合保存不重复元素，适合去重和成员测试：

```python
topics = {"变量", "循环", "变量"}
print(topics)                    # 只保留一个“变量”
print("循环" in topics)
```

集合没有用于业务逻辑的稳定顺序；不要依赖打印顺序。`a | b` 求并集，`a & b` 求交集，`a - b` 求差集。

字典用键映射到值：

```python
student = {"name": "小林", "score": 86}
student["score"] += 5
print(student.get("class", "未分班"))
```

使用 `get` 可以处理键不存在的情况；直接访问不存在的键会抛 `KeyError`。字典适合按名字查字段，但若字段集合固定且代码规模增大，可以考虑数据类或明确的类型。

一个常见陷阱是别名：`b = a` 不会复制列表，只是让两个名字指向同一个列表。浅复制 `a.copy()` 只复制外层；嵌套列表中的子列表仍共享。需要深复制时先确认是否真的需要，因为复杂对象可能包含文件、锁等不能简单复制的状态。

**练习**：用字典保存一名学生的姓名和分数，用列表保存三名学生，再用集合找出不重复的课程名。

## 第5章 条件、循环与分支

`if` 根据条件选择路径：

```python
score = 86
if score >= 90:
    level = "优秀"
elif score >= 60:
    level = "通过"
else:
    level = "继续练习"
```

冒号后的缩进块属于该分支。Python 用缩进表达结构，建议统一使用四个空格。多个条件用 `and`、`or`、`not` 组合；比较链可以写成 `0 <= score <= 100`。空字符串、零、空容器会被视为假，但需要表达业务含义时最好直接写清楚比较。

`for` 遍历一个可迭代对象：

```python
for index, topic in enumerate(["变量", "条件", "循环"], start=1):
    print(index, topic)
```

使用 `enumerate` 同时获得编号和值，比手动维护计数器更不易出错。`range(5)` 产生 `0` 到 `4`，终点不包含在内；`range(start, stop, step)` 可以调整起点和步长。遍历字典时，`items()` 可同时取键和值。

`while` 在条件为真时反复运行，必须确认每轮都会改变状态，或者在合适时机退出，否则会成为无限循环。`break` 立即结束最近一层循环；`continue` 跳到下一轮。循环也可带 `else`，它只在循环自然结束、没有被 `break` 打断时执行，适合表达“遍历后没有找到”的情况。

Python 3.10 起有 `match` 结构，用来按数据形状或固定模式分支。初学者先掌握 `if/elif`；只有模式匹配能明显表达结构时再用 `match`，不要只为显得新颖而使用。

**练习**：写一个猜数字程序：用户最多猜五次，程序给出偏大或偏小提示；猜中后结束，并准确显示是否在限制次数内成功。

## 第6章 函数：把步骤变成接口

函数给一段可复用逻辑命名。参数是调用者交给函数的数据，返回值是函数提供给调用者的结果：

```python
def average(scores: list[float]) -> float:
    if not scores:
        raise ValueError("至少需要一个分数")
    return sum(scores) / len(scores)
```

类型标注帮助编辑器和读者理解约定，但 Python 默认不会在运行时强制检查所有标注。函数应有单一、清楚的职责；与其编写一个处理输入、计算、打印、存档的大函数，不如拆成互相配合的小函数。

参数可以按位置或名称传入。默认值在函数定义时求值，所以不要用可变对象作为默认值：

```python
def add_topic(topic: str, topics: list[str] | None = None) -> list[str]:
    if topics is None:
        topics = []
    topics.append(topic)
    return topics
```

默认值 `[]` 会在不同调用之间共享同一个列表；使用 `None` 再在函数内部新建列表，可以避免这个问题。函数可以返回多个值，实际返回的是一个元组，调用方可用多个变量拆开接收。

局部变量只在函数内部有效。尽量通过参数传入依赖，通过返回值交付结果，而不是依靠大量全局变量。文档字符串放在函数体开头，说明目的、参数约束和返回值；注释解释“为什么这样做”，不要复述代码每个字符在做什么。

**练习**：分别实现 `parse_score(text)`、`is_pass(score)` 与 `format_report(name, score)`。每个函数只做一件事，并为无效分数定义一致行为。

## 第7章 推导式、迭代器与生成器

列表推导式用一个表达式构建新列表：

```python
scores = [86, 59, 92, 74]
passed = [score for score in scores if score >= 60]
```

左侧表达“取什么”，`for` 表达“从哪里取”，可选的 `if` 表达过滤条件。推导式适合简单转换；若需要嵌套多层、多个分支或副作用，普通循环通常更清楚。集合和字典也可以使用相似语法。

可迭代对象能被 `for` 遍历，例如列表、字符串、字典和文件对象。迭代器代表逐个产生项目的过程；调用 `next()` 会取下一个项目，取完时抛 `StopIteration`。大多数时候直接使用 `for`，无需手动操作协议。

生成器函数用 `yield` 逐步产出值：

```python
def squares(limit: int):
    for number in range(limit):
        yield number * number

for value in squares(4):
    print(value)
```

生成器不会一开始就建立所有结果，适合流式处理较大的数据。生成器通常只能从头遍历一次；如果同一结果要多次使用，应保存结果或重新创建生成器。生成器表达式 `(... for item in source)` 与列表推导式形式相似，但按需计算。

**练习**：写一个生成器，逐行读取文本并只产出非空行；再用列表推导式把这些行转换为去掉首尾空白的文本。比较两种方式的内存和可读性。

## 第8章 模块、包与程序入口

模块通常是一个 Python 文件。把代码拆成模块，可以让职责明确、测试更容易，也可以让其他程序重用。`import math` 导入模块，使用 `math.sqrt(9)` 调用其中的名字；`from pathlib import Path import ...` 是语法错误，正确写法是 `from pathlib import Path`。不要随意使用 `from module import *`，因为它会把不清楚来源的名字放进当前命名空间。

导入模块会执行模块顶层语句，因此模块顶层应只做定义和轻量初始化，不应一导入就启动网络服务、删除文件或运行长任务。脚本入口惯例：

```python
def main() -> None:
    print("从这里启动程序")

if __name__ == "__main__":
    main()
```

直接运行文件时，`__name__` 为 `"__main__"`；被其他模块导入时，`main()` 不会自动执行。这样同一文件既能作为命令运行，也能被测试代码导入。

多个模块可以组成包。常见结构是：

```text
study_tracker/
    __init__.py
    cli.py
    storage.py
    models.py
```

包内导入应与项目启动方式相匹配。项目增长后使用安装配置或 `python -m package.module` 启动，比依赖临时修改 `sys.path` 更稳定。

**练习**：把第7章的生成器放到 `text_tools.py`，另建 `main.py` 导入并调用它；验证直接运行 `text_tools.py` 不会意外开始处理文件。

## 第9章 文件、路径与结构化数据

文件读写是程序和外界交换数据的常见方式。优先使用 `pathlib.Path` 表示路径，用 `with` 管理文件生命周期：

```python
from pathlib import Path

path = Path("notes.txt")
with path.open("w", encoding="utf-8") as file:
    file.write("第一条笔记\n")
```

`with` 块结束后文件会自动关闭，即使中途发生异常也一样。读文本时指定编码，避免不同系统默认编码不一致。`"w"` 会清空旧文件；追加用 `"a"`；只读取用 `"r"`。保存重要数据时，先明确覆盖、追加和备份策略。

JSON 适合保存嵌套的结构化数据：

```python
import json
from pathlib import Path

data = {"name": "小林", "scores": [86, 92]}
path = Path("student.json")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
loaded = json.loads(path.read_text(encoding="utf-8"))
```

`json.dumps` 把 Python 对象变成 JSON 字符串，`json.loads` 则解析 JSON 字符串。文件损坏时解析会抛异常；不要把未知文件内容直接当作可信数据。CSV 适合行列数据，使用 `csv` 标准库处理引号、逗号和换行，比自己用 `split(",")` 安全。

**练习**：把多名学生的姓名与分数保存为 JSON，重新读取后求平均分。分别测试缺少文件、无效 JSON 和空列表。

## 第10章 错误、异常与资源清理

语法错误表示代码无法解析；异常是在程序运行过程中发生的问题，例如除以零、路径不存在或输入无法转换。Traceback 从调用过程列出异常发生的位置；阅读最底部的异常类型和消息，再回到相关代码检查。

只捕获你知道如何处理的异常：

```python
try:
    score = int(input("分数："))
except ValueError:
    print("请输入整数，例如 85")
else:
    print(f"你输入了 {score}")
finally:
    print("输入流程结束")
```

`except ValueError` 明确处理整数转换失败。`else` 只在没有异常时运行；`finally` 用于无论成功或失败都要执行的收尾操作。对于文件等资源，优先用 `with` 而不是手写 `finally`。

用 `raise` 在函数发现违反约定时报告错误。设计自己的异常类型时，让调用方可以有针对性地处理。不要写空的 `except:`，也不要捕获所有异常后只显示“失败”；这样会隐藏程序缺陷，用户也无法知道发生了什么。异常消息要说明输入要求或下一步操作，但不要泄露密码、令牌或完整敏感数据。

**练习**：为第9章的 JSON 读取增加清晰错误消息；区分文件缺失、JSON 语法错误、数据结构不符合预期三种情况。

## 第11章 类、对象与数据类

当数据和操作总是成组出现时，可以使用类来组织它们。类定义一类对象的结构；实例是具体对象；方法是以实例为第一个参数的函数：

```python
class Student:
    def __init__(self, name: str, score: int) -> None:
        self.name = name
        self.score = score

    def passed(self) -> bool:
        return self.score >= 60
```

`self` 指当前实例。`self.name` 属于这个学生；若在类体上直接定义一个可变列表，则所有实例可能意外共享它。实例属性适合每个对象不同的状态；类属性适合真正共享的常量或行为。

有些类主要用来承载数据，这时 `dataclasses` 可以减少样板代码：

```python
from dataclasses import dataclass

@dataclass
class StudentRecord:
    name: str
    score: int
```

`dataclass` 会自动提供初始化方法和可读的显示形式。若字段是列表等可变对象，要使用 `field(default_factory=list)`，而不是把 `[]` 当默认值。

继承表达“是一种”的关系，例如 `Teacher` 是 `Person` 的一种；组合表达“拥有”的关系，例如 `Course` 拥有若干 `StudentRecord`。初学者优先考虑组合，因为它通常让职责更灵活。类不是让每个数据都变复杂的理由：如果一个字典和几段函数更清晰，就先使用它们。

**练习**：用数据类表示课程和学生记录；写一个函数统计平均分与通过人数。评估统计逻辑放在独立函数还是方法里更容易测试。

## 第12章 标准库：解决常见问题的工具箱

标准库随 Python 一起提供，不用额外安装。先确认标准库是否已有合适工具，再决定是否引入第三方包。

- `pathlib`：表示和组合文件路径。
- `json`、`csv`：读写结构化文本。
- `datetime`：处理日期和时间；需要明确时区时使用带时区的时间对象。
- `collections.Counter`：计数；`defaultdict`：在缺省时构造值。
- `statistics`：计算常见统计量。
- `argparse`：为命令行程序解析选项。
- `logging`：按级别记录调试、运行和错误信息。
- `unittest`：编写标准库单元测试。

例如统计单词：

```python
from collections import Counter

words = ["变量", "循环", "变量", "函数"]
counts = Counter(words)
print(counts.most_common(2))
```

标准库文档非常完整，但模块能力不等于“应该全部使用”。选库时考虑数据规模、错误处理、可维护性和项目依赖。网络请求、密码学等领域尤其不要自己编写未经验证的算法。

**练习**：用 `argparse` 为一个文本统计工具增加 `--file` 参数；找不到文件时输出可理解的错误，而不是原始 traceback。

## 第13章 虚拟环境、pip 与依赖管理

不同项目可能需要不同版本的第三方库。虚拟环境为项目提供隔离的 Python 包目录，避免一个项目升级依赖后破坏另一个项目。

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install requests
```

使用 `python -m pip` 可以减少 `pip` 命令指向另一个 Python 安装的可能。安装后用 `python -m pip show requests` 或在 Python 中导入确认。`.venv` 通常不提交到 Git，因为它体积大且与操作系统相关；项目应该记录如何重建环境。

依赖文件应来自项目实际需要，并尽量记录经过验证的版本范围。不要随意安装与任务无关的包；安装前核对名称和来源，避免把拼错的包名当作真实依赖。API 密钥不能写入源码或依赖清单，应放在环境变量或受控配置中。

**练习**：新建一个虚拟环境，安装一个小型第三方包，退出环境后观察导入结果，再重新激活确认隔离效果。

## 第14章 测试、调试与代码风格

测试把“我觉得能用”变成可重复检查的例子。先写输入和预期输出，再检查真实结果。单元测试围绕一个小函数，集成测试检查多个模块的协作。

```python
import unittest

def is_pass(score: int) -> bool:
    return score >= 60

class ScoreTests(unittest.TestCase):
    def test_boundary(self) -> None:
        self.assertFalse(is_pass(59))
        self.assertTrue(is_pass(60))

if __name__ == "__main__":
    unittest.main()
```

边界值最容易暴露错误：空列表、最小值、最大值、恰好达到阈值、缺失文件。调试时先建立最小复现，再逐步缩小问题范围。打印中间变量能快速定位入门问题；复杂问题可使用断点调试器或日志。

风格的一致性能减轻阅读负担：名字说明意图，函数短而聚焦，避免深层嵌套，数据验证靠近输入边界。不要为了追求“聪明”把所有逻辑压进一行。代码能读懂、能测试、能修改，比字符数少更重要。

**练习**：为第6章的平均分函数添加空输入、一个分数和多个分数的测试；确认异常类型符合约定。

## 第15章 异步任务入门

普通函数按调用顺序执行。异步适合等待网络、文件或其他外部操作时，让程序在等待期间处理别的任务；它不会自动让纯计算变快。

```python
import asyncio

async def fetch_name(name: str) -> str:
    await asyncio.sleep(1)  # 用于示意异步等待，不是真实网络请求
    return f"完成：{name}"

async def main() -> None:
    results = await asyncio.gather(
        fetch_name("任务 A"),
        fetch_name("任务 B"),
    )
    print(results)

asyncio.run(main())
```

`async def` 定义协程函数，调用它会得到一个需要运行的协程对象；`await` 在异步函数中等待协程完成；`asyncio.run` 是简单程序的入口。实际网络请求要使用支持异步的客户端，否则在事件循环里运行阻塞调用会卡住其他任务。

CPU 密集型计算通常考虑进程或专门的计算库。线程适合部分阻塞等待场景，但共享状态需要同步。并发会增加错误处理和取消逻辑的复杂度，应先有性能或响应性需求再引入。

**练习**：把两个不同延迟的异步函数交给 `gather`，记录总耗时。解释为什么等待并发不等于 CPU 同时执行。

## 第16章 综合项目：学习记录命令行工具

我们把本书的内容组合成一个小程序：从 JSON 文件读取学习记录、添加新记录、统计总时长。这个项目刻意只用标准库，帮助你看到模块、函数、异常、文件和命令行参数如何协作。

将下面的代码保存为 `study_log.py`：

```python
import argparse
import json
from datetime import date
from pathlib import Path

DATA_FILE = Path("study-log.json")

def load_entries() -> list[dict[str, object]]:
    if not DATA_FILE.exists():
        return []
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"记录文件不是有效 JSON：{error}") from error
    if not isinstance(data, list):
        raise ValueError("记录文件最外层必须是列表")
    return data

def save_entries(entries: list[dict[str, object]]) -> None:
    text = json.dumps(entries, ensure_ascii=False, indent=2)
    DATA_FILE.write_text(text, encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser(description="记录今天学了什么")
    parser.add_argument("--topic", required=True, help="学习主题")
    parser.add_argument("--minutes", required=True, type=int, help="学习分钟数")
    args = parser.parse_args()
    if args.minutes <= 0:
        parser.error("分钟数必须大于零")
    try:
        entries = load_entries()
    except ValueError as error:
        parser.error(str(error))
    entries.append({"date": date.today().isoformat(), "topic": args.topic, "minutes": args.minutes})
    save_entries(entries)
    total = sum(int(entry["minutes"]) for entry in entries)
    print(f"已记录 {args.topic}；累计学习 {total} 分钟。")

if __name__ == "__main__":
    main()
```

运行示例：`python study_log.py --topic "列表与字典" --minutes 25`。每运行一次就新增一条记录。程序当前把错误 JSON 转成清楚提示；若只输出异常消息，排错时仍应在开发阶段保留 traceback 日志。这个示例没有解决并发写文件：多人同时写入可能互相覆盖。若要支持多人或大量数据，应换用数据库并增加验证与备份。

把项目继续完善：增加 `--list` 查看记录；拒绝空主题；让输出按日期排序；为读写、统计分别写测试；最后在全新虚拟环境运行一遍。

## 资料来源与适用范围

本书是独立撰写的中文教材，未复制官方教程正文。术语与语言行为按 Python 官方资料核对，内容核对日期为 2026-09-23。Python 版本跨度较大时，先用 `python --version` 确认环境，再查对应版本文档。

- Python 官方教程（3.14）：https://docs.python.org/3/tutorial/
- Python 语言参考：https://docs.python.org/3/reference/
- Python 标准库：https://docs.python.org/3/library/
- 虚拟环境与包：https://docs.python.org/3/tutorial/venv.html
