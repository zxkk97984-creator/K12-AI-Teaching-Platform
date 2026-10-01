# Python 编程：从入门到实践

- **原书**：Python Crash Course, 3rd Edition
- **作者**：[美] Eric Matthes
- **译者/出版**：袁国忠 译，人民邮电出版社（图灵丛书），2023
- **真实目录来源**：中国海洋大学图书馆 OPAC、作者官网 https://ehmatthes.github.io/pcc_3e/
- **本文件说明**：基于该书第3版真实20章结构整理知识点，**非逐字原文**（原书受版权保护），代码示例为教学改写。

---

## 第一部分 基础知识

### 第 1 章 起步

#### 1.1 为什么学 Python

你每天用手机刷短视频、用电脑查资料、用学习软件做作业——这些背后都是程序在运行。程序是人写的，而写程序就是"编程"。那为什么选 Python 呢？

Python 是目前世界上最受欢迎的编程语言之一。它的语法接近日常英语，没有那么多奇怪的符号。你看这行 Python 代码：`print("你好")`——即使没学过编程，你大概也能猜到它是在屏幕上打印"你好"两个字。这就是 Python 的设计哲学：让人类读起来舒服。

对比一下其他语言。C 语言写 Hello World 要写一堆头文件；Java 要先建类、写 main 方法，啰嗦得很。Python 一行就搞定。这就是为什么全世界初中生学编程基本都从 Python 入门。

今天你用它画个图，明天就能用它做一个网站，后天就能用它跑一个 AI 模型。初中生学 Python 的好处是：第一学期就能写出能跑的小游戏，成就感很强；而且它在人工智能、数据分析、网站后端、自动化办公领域都很常用，以后无论走哪个方向都用得上。

#### 1.2 安装 Python

从 python.org 下载安装包。Windows 用户安装时**务必勾选 "Add Python to PATH"**，否则后面在命令行里找不到 python。PATH 是什么？你可以理解成"电脑去哪里找程序的路线表"。勾了它，电脑才知道你装的 Python 在哪里。

装完后打开命令行（按 Win+R 输入 cmd 回车），输入 `python --version`。能看到类似 `Python 3.12.0` 就说明装好了。如果提示"不是内部命令"，说明 PATH 没勾，重装一次记得勾上。

#### 1.3 安装 VS Code

VS Code 是微软出的免费代码编辑器。你可以把它理解成"专门写代码的 Word"。装完后在扩展市场搜 Python，安装官方扩展。它会自动帮你高亮报错、补全代码、一键运行。

#### 1.4 Hello World

新建一个文件夹（比如在桌面建 `mycode`），在里面新建 `hello.py`：

```python
print("Hello, world!")
```

右键选 Run Python File，屏幕显示 `Hello, world!`。这是你的第一个程序。

`print` 是 Python 里最常用的命令，意思是"打印到屏幕"。括号里的内容就是要打印的东西。引号表示这是一段文字。

再试几个：

```python
print("我是小明")
print(1 + 1)
print("你好" + "世界")
```

第二个会输出 2，第三个会输出 你好世界。

**练习**：
1. 写一个程序，打印你的名字、年龄、学校，各占一行。
2. 写一个程序，打印 100 减 37 的结果。

**常见误区**：
- 文件名不要叫 `python.py`，会和 Python 自己冲突。
- 文件名不要有中文和空格。
- 代码里的引号必须是英文引号，不能用中文引号。
- 括号必须是英文括号，不能是中文括号。

### 第 2 章 变量和简单数据类型

#### 2.1 变量

变量就是给一个数据起名字，方便以后使用。你可以把它想象成一个贴了标签的盒子，盒子里装着数据。

```python
message = "Hello Python world!"
print(message)
```

你随时可以改变盒子里装的东西：

```python
message = "Hello Python world!"
print(message)
message = "Python is fun."
print(message)
```

变量名只能用字母、数字、下划线，不能以数字开头，不能有空格。比如 `message_1` 合法，`1message` 和 `message-1` 不合法。Python 约定俗成用小写字母加下划线命名，比如 `user_name` 而不是 `UserName`。

#### 2.2 字符串

字符串就是文字，用单引号或双引号包起来：

```python
name = "ada lovelace"
print(name.title())
print(name.upper())
print(name.lower())
```

`.title()` 每个单词首字母大写，`.upper()` 全大写，`.lower()` 全小写。

拼接字符串用 f-string（Python 3.6 以后推荐）：

```python
first = "ada"
last = "lovelace"
full = f"{first} {last}"
print(f"Hello, {full.title()}!")
```

f-string 在引号前加 `f`，里面用 `{}` 嵌变量，比用 `+` 拼接清楚得多。

其他常用字符串操作：

```python
print("  hello  ".strip())
print("hello".replace("l", "L"))
print("a,b,c".split(","))
print("hello".count("l"))
```

`.strip()` 去首尾空格；`.replace(旧, 新)` 替换；`.split(分隔符)` 把字符串切成列表；`.count(子串)` 数字串出现几次。

#### 2.3 数字

```python
print(2 + 3)
print(3 ** 2)
print(10 % 3)
print(10 // 3)
print(10 / 3)
```

`**` 是乘方；`%` 取余；`//` 整除；`/` 普通除法（结果一定是小数）。注意 `0.1 + 0.2` 不等于 `0.3`，这是浮点数近似存储的普遍现象，不是 bug。

#### 2.4 注释与 Python 之禅

注释用 `#`，给人看，Python 不执行。写代码时要写注释说明"为什么这么做"。在交互式环境输入 `import this` 会看到《Python 之禅》。

**练习**：
1. 建三个变量存你的姓名、年龄、身高，用 f-string 打印一句话。
2. 输入圆的半径，输出面积（π 取 3.14159）。

**常见误区**：字符串和数字不能直接相加，比如 `"age" + 13` 会报错，要先 `str(13)` 转字符串。

### 第 3 章 列表

#### 3.1 列表是什么

列表用方括号 `[]`，里面按顺序放数据：

```python
bicycles = ["trek", "cannondale", "redline", "specialized"]
print(bicycles[0])
print(bicycles[-1])
```

下标从 0 开始，所以第一个元素是 `[0]`；`-1` 取最后一个，`-2` 取倒数第二个。列表里可以放任何类型的数据，甚至不同类型混着放：`mixed = ["小明", 13, 1.65, True]`。

#### 3.2 修改、添加、删除

```python
motorcycles = ["honda", "yamaha", "suzuki"]
motorcycles[0] = "ducati"
motorcycles.append("bmw")
motorcycles.insert(0, "harley")
del motorcycles[0]
popped = motorcycles.pop()
motorcycles.remove("yamaha")
```

`.append()` 加末尾；`.insert(下标, 值)` 在指定位置插入；`del` 按下标删；`.pop()` 弹出末尾并返回它；`.remove(值)` 按值删（只删第一个匹配）。

#### 3.3 组织列表

```python
cars = ["bmw", "audi", "toyota", "subaru"]
cars.sort()
cars.sort(reverse=True)
print(sorted(cars))
cars.reverse()
print(len(cars))
```

`.sort()` 永久排序（改变原列表）；`sorted()` 临时排序（返回新列表）；`.reverse()` 反转；`len()` 长度。

**练习**：建一个列表存 5 个同学的名字，排序后打印。

**常见误区**：`sort()` 是永久的，排完就回不去了；要保留原顺序用 `sorted()`。

### 第 4 章 操作列表

#### 4.1 遍历

```python
magicians = ["alice", "david", "carolina"]
for m in magicians:
    print(m)
```

`for m in magicians` 把列表里每个元素依次取出来赋给 `m`，循环体缩进的部分都会执行。注意冒号不能少，循环体必须缩进。

#### 4.2 range 与统计

```python
for v in range(1, 5):
    print(v)

nums = list(range(1, 6))
squares = [x**2 for x in range(1, 11)]
print(squares)
print(min(squares), max(squares), sum(squares))
```

`range(1, 5)` 产生 1,2,3,4（不包含5）。列表推导式 `[x**2 for x in range(1,11)]` 一行生成平方数列表，非常常用。

#### 4.3 切片

```python
players = ["a", "b", "c", "d", "e"]
print(players[0:3])
print(players[2:])
print(players[-2:])
```

切片 `[起:止]` 包含起点不包含终点。省略起点从头开始，省略终点到末尾。

#### 4.4 元组

```python
dimensions = (200, 50)
print(dimensions[0])
```

元组用圆括号，创建后不能修改。适合存固定数据，比如画布尺寸。

**练习**：用列表推导式生成 1 到 10 的立方数。

### 第 5 章 if 语句

程序不是一条路走到黑，它需要根据情况做选择。这就是 if 语句：

```python
age = 12
if age < 4:
    print("免费")
elif age < 18:
    print("5 元")
else:
    print("10 元")
```

判断相等用 `==`（两个等号），不等于用 `!=`，包含用 `in`。`elif` 是"否则如果"，可以写多个；`else` 是兜底。

```python
banned = ["andrew", "carolina"]
user = "marie"
if user in banned:
    print("禁止入内")
else:
    print("欢迎")
```

**练习**：输入成绩，90以上输出"优秀"，80以上"良好"，60以上"及格"，否则"要加油"。

**常见误区**：`if age = 18` 是错的（单等号是赋值），要用 `==`。

### 第 6 章 字典

#### 6.1 字典是什么

列表是按下标查数据，有时候你不想用数字下标，想用名字查。比如查同学的分数，你想用 `students["小红"]` 而不是 `students[0]`。这就是字典：按键查值。

```python
alien = {"color": "green", "points": 5}
print(alien["color"])
```

字典用花括号 `{}`，里面是一对一对的"键: 值"。键是名字，值是数据。

#### 6.2 修改、添加、删除

```python
alien = {"color": "green", "points": 5}
alien["x"] = 0
alien["color"] = "yellow"
del alien["points"]
print(alien)
```

键已经存在就修改值，不存在就添加新键值对。

#### 6.3 遍历

```python
for k, v in alien.items():
    print(k, v)
for k in alien.keys():
    print(k)
for v in alien.values():
    print(v)
```

#### 6.4 嵌套

真实数据经常是"列表里套字典"：

```python
aliens = [
    {"color": "green", "points": 5},
    {"color": "yellow", "points": 10}
]
for a in aliens:
    print(a)
```

**练习**：建一个字典存"语文/数学/英语"三科分数，输出总分和平均分。

**常见误区**：字典的键必须是不可变的（字符串、数字可以，列表不行）。

### 第 7 章 用户输入和 while 循环

#### 7.1 input

```python
name = input("你叫什么？")
print(f"你好 {name}")

age = int(input("你几岁？"))
print(f"明年 {age+1} 岁")
```

`input()` 拿到的永远是字符串。哪怕你输入 `13`，它拿到的也是 `"13"`，要做数学必须先 `int()` 转。这是新手最常踩的坑。

#### 7.2 while 循环

```python
current = 1
while current <= 5:
    print(current)
    current += 1
```

`while` 后面的条件为真就一直循环。记得在循环体里改变量，否则会死循环。

#### 7.3 break 与 continue

```python
while True:
    line = input("> ")
    if line == "q":
        break
    if line.startswith("#"):
        continue
    print(line)
```

`break` 立刻跳出整个循环；`continue` 跳过本次剩下的语句。

**练习**：用 while 不断让用户输入数字，直到输入 0 结束，输出平均值。

**常见误区**：`input` 不转类型直接做加法会报 TypeError。

### 第 8 章 函数

#### 8.1 定义与参数

函数就是把一段代码打包好，起个名字，以后反复调用。

```python
def greet(username):
    print(f"Hello, {username}!")

greet("xiaoming")
```

#### 8.2 默认参数与返回值

```python
def describe_pet(name, animal="狗"):
    print(f"{name} 是一只{animal}")
    return name

describe_pet("旺财")
describe_pet("咪咪", "猫")
```

`animal="狗"` 是默认参数。`return` 把结果送回去；没有 `return` 的函数返回 `None`。

#### 8.3 任意数量参数

```python
def make_pizza(*toppings):
    for t in toppings:
        print(t)
```

`*toppings` 把多个参数打包成元组。

**练习**：写一个函数 `bmi(weight, height)` 返回 BMI 值。

**常见误区**：函数里的变量是局部变量，函数外面用不了。

### 第 9 章 类

#### 9.1 创建和使用类

类是图纸，对象是按图纸造出来的具体东西。比如"学生"是一个类，"小红"是这个类的一个具体对象。

```python
class Dog:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def sit(self):
        print(f"{self.name} 坐下了")

my_dog = Dog("旺财", 3)
my_dog.sit()
```

`__init__` 是构造方法，创建对象时自动调用；`self` 代表对象自己。

#### 9.2 继承

```python
class Car:
    def __init__(self, make, model, year):
        self.make = make
        self.model = model
        self.year = year

class ElectricCar(Car):
    def __init__(self, make, model, year):
        super().__init__(make, model, year)
        self.battery = 75

tesla = ElectricCar("tesla", "model 3", 2024)
```

`ElectricCar(Car)` 表示继承 Car，自动拥有 Car 的所有方法。

**练习**：定义一个 `Student` 类，有姓名和分数两个属性，有一个 `show` 方法打印信息。

**常见误区**：`__init__` 前后是两个下划线，不是一个。

### 第 10 章 文件和异常

```python
with open("note.txt", encoding="utf-8") as f:
    content = f.read()

with open("note.txt", "w", encoding="utf-8") as f:
    f.write("Hello\n")

try:
    result = 10 / int(input("除数："))
except ZeroDivisionError:
    print("不能除 0")
else:
    print(result)

import json
with open("data.json", "w") as f:
    json.dump([1, 2, 3], f)
```

### 第 11 章 测试代码

测试就是写一段代码，自动检查你写的函数对不对。改了代码后难道要每次都手动测一遍？测试就是自动化这个过程。

```python
import unittest

def add(a, b):
    return a + b

class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)

if __name__ == "__main__":
    unittest.main()
```

`assertEqual(实际值, 期望值)` 判断两者是否相等。

**练习**：给第8章写的 `bmi` 函数配一个测试。

**常见误区**：测试要测正常情况和边界情况（比如 0、负数）。

---

## 第二部分 项目（思路版）

### 第 12—14 章 外星人入侵

```python
import sys
import pygame

pygame.init()
screen = pygame.display.set_mode((800, 600))

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            sys.exit()
    screen.fill((230, 230, 230))
    pygame.display.flip()
```

### 第 15—17 章 数据可视化

```python
import matplotlib.pyplot as plt
x = [1, 2, 3, 4, 5]
y = [1, 4, 9, 16, 25]
plt.plot(x, y, marker="o")
plt.show()
```

### 第 18—20 章 Web 应用

Django 是 Python 的 Web 框架。初中阶段了解"Web 应用 = 后端 Python + 数据库 + 浏览器页面"即可。

---

## 附录：14 个完整小项目

### 项目 1：猜数字

```python
import random
answer = random.randint(1, 100)
tries = 0
while True:
    g = int(input("猜 1-100："))
    tries += 1
    if g == answer:
        print(f"对了！用了{tries}次")
        break
    elif g < answer:
        print("太小")
    else:
        print("太大")
```

### 项目 2：石头剪刀布

```python
import random
c = random.choice(["石头", "剪刀", "布"])
p = input("出：")
print(f"你{p} 电脑{c}")
if p == c: print("平")
elif (p=="石头" and c=="剪刀") or (p=="剪刀" and c=="布") or (p=="布" and c=="石头"):
    print("你赢")
else:
    print("你输")
```

### 项目 3：计算器

```python
a = float(input("数1："))
op = input("+-*/：")
b = float(input("数2："))
if op == "+": print(a+b)
elif op == "-": print(a-b)
elif op == "*": print(a*b)
elif op == "/":
    print("不能除0" if b==0 else a/b)
```

### 项目 4：词频统计

```python
text = "the cat sat on the mat"
words = text.split()
counter = {}
for w in words:
    counter[w] = counter.get(w, 0) + 1
for k, v in counter.items():
    print(k, v)
```

### 项目 5：凯撒密码

```python
plain = input("英文：")
s = 3
out = ""
for ch in plain:
    if "a" <= ch <= "z":
        out += chr((ord(ch)-ord("a")+s)%26+ord("a"))
    else:
        out += ch
print(out)
```

### 项目 6：温度转换

```python
c = float(input("摄氏："))
print("华氏", c*9/5+32)
```

### 项目 7：记账本

```python
records = []
while True:
    op = input("1记账2账单3退：")
    if op == "1":
        records.append((input("花哪："), float(input("金额："))))
    elif op == "2":
        for i, v in records: print(i, v)
        print("合计", sum(v for _, v in records))
    elif op == "3": break
```

### 项目 8：通讯录

```python
contacts = {}
while True:
    op = input("1加2查3全部4退：")
    if op == "1":
        contacts[input("名：")] = input("电话：")
    elif op == "2":
        print(contacts.get(input("查："), "没这人"))
    elif op == "3":
        for k, v in contacts.items(): print(k, v)
    elif op == "4": break
```

### 项目 9：成绩管理

```python
students = []
while True:
    op = input("1录2看3平均4退：")
    if op == "1":
        students.append((input("名："), float(input("分："))))
    elif op == "2":
        for n, s in students: print(n, s)
    elif op == "3":
        if students: print(sum(s for _, s in students)/len(students))
    elif op == "4": break
```

### 项目 10：单词本

```python
words = {}
while True:
    op = input("1加2查3默写4退：")
    if op == "1":
        words[input("英：")] = input("中：")
    elif op == "2":
        print(words.get(input("查："), "无"))
    elif op == "3":
        for en, cn in words.items():
            a = input(en+"=")
            print("对" if a==cn else "错，是"+cn)
    elif op == "4": break
```

### 项目 11：BMI 计算器

```python
h = float(input("身高米："))
w = float(input("体重kg："))
bmi = w/(h*h)
print(f"BMI={bmi:.1f}")
print("偏瘦" if bmi<18.5 else "正常" if bmi<24 else "偏胖")
```

### 项目 12：掷骰子

```python
import random
n = int(input("掷几次："))
counts = [0]*6
for _ in range(n):
    counts[random.randint(1,6)-1] += 1
for i in range(6): print(f"{i+1}:{counts[i]}次")
```

### 项目 13：九九乘法表

```python
for i in range(1, 10):
    for j in range(1, i+1):
        print(f"{j}×{i}={i*j}", end="\t")
    print()
```

### 项目 14：猜成语

```python
import random
idioms = {"画蛇添足":"多此一举", "守株待兔":"抱侥幸心理"}
ans = random.choice(list(idioms))
print("提示：", idioms[ans])
g = input("猜：")
print("对" if g==ans else "是"+ans)
```

---

> 本文件基于《Python 编程：从入门到实践》第3版真实章节结构整理，代码示例为教学改写。原书受版权保护，深入学习请购买正版。
