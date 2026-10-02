#!/usr/bin/env python3
"""Generate the 12 offline K12 autoplay lessons, manifests, covers, and catalog."""
from __future__ import annotations
import json
import math
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
RUNTIME = (SOURCE / "runtime.js").read_text(encoding="utf-8")
SUBJECT = "计算机与人工智能"
STAGES = {
    "PRIMARY_LOWER": ("小学低段", "1—3 年级"),
    "PRIMARY_UPPER": ("小学高段", "4—6 年级"),
    "JUNIOR": ("初中", "7—9 年级"),
    "SENIOR": ("高中", "10—12 年级"),
}
COLORS = {"red": "红", "blue": "蓝", "yellow": "黄", "green": "绿"}
SHAPES = {"circle": "圆形", "triangle": "三角形", "square": "方形"}


def scene(title, text, state):
    return {"title": title, "text": text, "state": state}


def bubble_states(values):
    cards = [{"id": str(i), "value": v} for i, v in enumerate(values)]
    result = []
    pass_no = 1
    end = len(cards)
    while end > 1:
        for i in range(end - 1):
            before = [dict(card) for card in cards]
            left, right = cards[i], cards[i + 1]
            swapped = left["value"] > right["value"]
            reason = f"{left['value']} 比 {right['value']} 大" if swapped else f"{left['value']} 不大于 {right['value']}"
            if swapped:
                cards[i], cards[i + 1] = cards[i + 1], cards[i]
            result.append({
                "pass": pass_no, "left": i, "right": i + 1, "swap": swapped,
                "cards": [dict(card) for card in cards], "previousCards": before,
                "note": f"第 {pass_no} 轮：{left['value']} 和 {right['value']} 相邻比较；{reason}，所以{'交换位置' if swapped else '保持原位'}。",
                "text": f"第 {pass_no} 轮比较第 {i+1} 和第 {i+2} 张卡。{reason}，{'把较大的数向右交换一格。' if swapped else '顺序已经合适，不交换。'}"
            })
            if i == end - 2:
                result[-1]["note"] += f" 这一轮结束，当前最大值 {cards[-1]['value']} 已移到后面。"
                result[-1]["text"] += f" 这一轮结束，当前最大的数 {cards[-1]['value']} 已经移到后面。"
        pass_no += 1
        end -= 1
    return result, cards


def sort_groups(items, rule, previous=None):
    order = ["circle", "triangle", "square"] if rule == "shape" else ["red", "blue", "yellow"]
    buckets = [[] for _ in order]
    for item in items:
        key = item["shape"] if rule == "shape" else item["color"]
        buckets[order.index(key)].append(dict(item))
    centers = [160, 480, 800]
    for g, bucket in enumerate(buckets):
        for j, item in enumerate(bucket):
            item["x"] = centers[g]
            item["y"] = 178 + j * 92
            old = (previous or {}).get(item["id"], (item["x"], item["y"]))
            item["from_x"], item["from_y"] = old
    positions = {item["id"]: (item["x"], item["y"]) for bucket in buckets for item in bucket}
    return buckets, positions


def move_robot(commands, walls, goal):
    dirs = {"→": (0, 1), "↓": (1, 0), "←": (0, -1), "↑": (-1, 0)}
    pos = (0, 0)
    path = [list(pos)]
    states = []
    for i, cmd in enumerate(commands):
        before = pos
        d = dirs[cmd]
        nxt = (pos[0] + d[0], pos[1] + d[1])
        if not (0 <= nxt[0] < 5 and 0 <= nxt[1] < 5) or list(nxt) in walls:
            states.append({"position": list(pos), "previous": list(pos), "path": path[:], "commands": commands[:], "current": i, "status": "blocked", "walls": walls, "goal": goal, "note": f"第 {i+1} 条指令遇到障碍或边界，立即停止。"})
            return states
        pos = nxt
        path.append(list(pos))
        done = list(pos) == goal
        states.append({"position": list(pos), "previous": list(before), "path": path[:], "commands": commands[:], "current": i, "status": "done" if done else "moving", "walls": walls, "goal": goal, "note": "到达终点。" if done else f"执行第 {i+1} 条指令，机器人只移动一格。"})
        if done:
            break
    return states


def pixel_data():
    # A 4x4 pattern expanded to a 2x2 block pattern; both grids represent the same image.
    coarse = [list(row) for row in [".##.", "#aa#", "#bb#", ".##."]]
    fine = [[coarse[r // 2][c // 2] for c in range(8)] for r in range(8)]
    return coarse, fine


def linear_steps(array, target, missing=False):
    steps = []
    checked = []
    for i, value in enumerate(array):
        found = value == target
        checked2 = checked + [i]
        code_line = 2 if found else (1 if not checked else 3)
        if missing:
            sentence = f"目标改为 {target}。下标 {i} 的值是 {value}，与目标不同；检查后继续向右。" if not found else f"下标 {i} 的值是 {value}，等于目标 {target}。"
        else:
            sentence = f"现在检查第 {i+1} 项，数值是 {value}。它{'等于' if found else '不等于'}目标 {target}。" + (" 找到后立即停止。" if found else " 所以继续检查下一项。")
        steps.append(scene("逐项检查", sentence, {"array": array, "target": target, "current": i, "checked": checked2, "codeLine": code_line, "note": f"当前比较：{value} {'=' if found else '≠'} {target}；日常位置是第 {i+1} 项，下标是 {i}。" if found else f"当前比较：{value} ≠ {target}；继续检查，不跳过任何一项。"}))
        checked = checked2
        if found:
            break
    if not missing:
        # Last comparison scene itself is the found stop state.
        steps[-1]["title"] = "找到目标并停止"
        steps[-1]["text"] = f"找到 {target} 了！它是第 {checked[-1]+1} 项，下标为 {checked[-1]}。线性查找在这里停止。"
        steps[-1]["state"]["note"] = f"找到：第 {checked[-1]+1} 项；下标 {checked[-1]}。不再检查后面的数据。"
    else:
        steps[-1]["title"] = "全部检查，未找到"
        steps[-1]["text"] = f"六项都检查过了，没有 {target}。现在显示“未找到”，并在数组结束处停止，没有越界。"
        steps[-1]["state"]["current"] = None
        steps[-1]["state"]["codeLine"] = 3
        steps[-1]["state"]["note"] = f"检查完 {len(array)} 项：未找到 {target}；数组已结束。"
    return steps


def nearest(xy, train):
    best = None
    best_d = float("inf")
    for p in train:
        d = (xy[0] - p["xy"][0]) ** 2 + (xy[1] - p["xy"][1]) ** 2
        if d < best_d:
            best, best_d = p, d
    return dict(best, distance=math.sqrt(best_d), distance_squared=best_d)


def dijkstra(nodes, edges, start):
    dist = {v: math.inf for v in nodes}
    prev = {v: None for v in nodes}
    dist[start] = 0
    settled = []
    events = []
    while len(settled) < len(nodes):
        candidates = [v for v in nodes if v not in settled and dist[v] < math.inf]
        if not candidates:
            break
        u = min(candidates, key=lambda v: (dist[v], nodes.index(v)))
        current_updates = []
        for a, b, w in edges:
            v = b if a == u else a if b == u else None
            if v is None or v in settled:
                continue
            old = dist[v]
            candidate = dist[u] + w
            updated = candidate < old
            current_updates.append({"from": u, "to": v, "weight": w, "base": dist[u], "candidate": candidate, "old": None if old == math.inf else old, "updated": updated})
            if updated:
                dist[v], prev[v] = candidate, u
        settled.append(u)
        events.append({"selected": u, "dist": dict(dist), "prev": dict(prev), "settled": settled[:], "relaxations": current_updates})
    return {"dist": dist, "prev": prev, "settled": settled, "events": events}


def path_to(prev, start, end):
    path, cur = [], end
    while cur is not None:
        path.insert(0, cur)
        if cur == start:
            return path
        cur = prev[cur]
    return []


def metrics(records, threshold):
    out = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    events = []
    for r in records:
        predicted = "spam" if r["score"] >= threshold else "normal"
        key = "tp" if r["truth"] == "spam" and predicted == "spam" else "fp" if r["truth"] == "normal" and predicted == "spam" else "fn" if r["truth"] == "spam" else "tn"
        out[key] += 1
        events.append({"id": r["id"], "truth": r["truth"], "score": r["score"], "predicted": predicted, "bucket": key, "counts": dict(out), "threshold": threshold})
    total = sum(out.values())
    result = {
        "counts": out,
        "accuracy": None if not total else (out["tp"] + out["tn"]) / total,
        "precision": None if out["tp"] + out["fp"] == 0 else out["tp"] / (out["tp"] + out["fp"]),
        "recall": None if out["tp"] + out["fn"] == 0 else out["tp"] / (out["tp"] + out["fn"]),
        "events": events,
    }
    return result


def build_lessons():
    lessons = []

    # PRIMARY_LOWER 1: input, fixed rule, output
    key = "primary-lower-input-process-output"
    title = "小机器人收到指令以后会做什么"
    rules = {"按键 A": "收到 A，就点亮圆灯", "按键 B": "收到 B，就点亮三角灯"}
    steps = [
        scene("观察一台小设备", "按下一个按键以后，设备会怎样做？我们跟着画面看一遍。", {"stage":"idle","input":None,"output":None,"rule":"先看看信息怎样变成结果"}),
        scene("认识三个位置", "左边是按键，中间的小设备照着写好的规则处理，右边显示结果。", {"stage":"idle","input":None,"output":None,"rule":"按键 A 点亮圆灯；按键 B 点亮三角灯"}),
        scene("收到按键 A", "按键 A 作为输入，沿着箭头进入设备。设备收到的是一个简单指令。", {"stage":"input","input":"按键 A","prev_stage":"idle","output":None,"rule":rules["按键 A"]}),
        scene("按规则处理", "设备里的规则说：收到 A，就让圆灯亮起来。中间的处理区域现在亮起。", {"stage":"process","input":"按键 A","prev_stage":"input","output":None,"rule":rules["按键 A"]}),
        scene("圆灯亮起", "规则执行以后，右边出现圆灯。输入按键 A，结果是圆灯亮。", {"stage":"output","input":"按键 A","prev_stage":"process","output":"圆灯亮","rule":rules["按键 A"]}),
        scene("换成按键 B", "现在换一个输入：按键 B。信息再次进入设备，规则也换成 B 对应的规则。", {"stage":"input","input":"按键 B","prev_stage":"output","output":None,"rule":rules["按键 B"]}),
        scene("三角灯亮起", "收到 B 后，设备照规则点亮三角灯。不同输入可以得到不同输出。", {"stage":"output","input":"按键 B","prev_stage":"input","output":"三角灯亮","rule":rules["按键 B"]}),
        scene("记住输入、处理、输出", "按键是输入，照规则办事是处理，灯亮是输出。我们看到的是一台设备按规则工作。", {"stage":"output","input":"按键 B","prev_stage":"input","output":"三角灯亮","rule":"输入 → 处理 → 输出"}),
    ]
    lessons.append({"key":key,"file":"input-process-output","stage":"PRIMARY_LOWER","title":title,"grades":"1—3 年级","kind":"input-process-output","subject":SUBJECT,"objective":"理解收到信息、按照规则处理、给出结果的基本顺序。","summary":"按键进入设备，设备按明确规则处理，并显示对应的灯光结果。","knowledge_points":["输入","处理","输出"],"data":{"rules":rules},"steps":steps})

    # PRIMARY_LOWER 2: rule-based grouping
    key="primary-lower-sorting-by-rule"; title="给图形找家：按规则分类"
    items=[
        {"id":"a","shape":"circle","shapeName":"圆形","color":"red","colorName":"红色"},
        {"id":"b","shape":"circle","shapeName":"圆形","color":"blue","colorName":"蓝色"},
        {"id":"c","shape":"triangle","shapeName":"三角形","color":"yellow","colorName":"黄色"},
        {"id":"d","shape":"triangle","shapeName":"三角形","color":"red","colorName":"红色"},
        {"id":"e","shape":"square","shapeName":"方形","color":"blue","colorName":"蓝色"},
        {"id":"f","shape":"square","shapeName":"方形","color":"yellow","colorName":"黄色"},
    ]
    pool=[];layout={}
    for i,item in enumerate(items):
        x,y=190+(i%3)*285,220+(i//3)*105
        pool.append(dict(item,x=x,y=y,from_x=x,from_y=y));layout[item["id"]]=(x,y)
    s2=[scene("先看图形", "这些图形有不同颜色，也有圆形、三角形和方形。先选一种规则来分。", {"stage":"pool","items":pool,"rule":"shape","note":"颜色和形状是两种不同特征。"})]
    s2.append(scene("先定形状规则", "这一轮按形状分类。我们只看形状，颜色先放在一边。", {"stage":"pool","items":pool,"rule":"shape","note":"当前规则：按形状分类。"}))
    groups,layout=sort_groups(items,"shape",layout)
    s2.append(scene("图形进入对应区域", "圆形进圆形区，三角形进三角形区，方形进方形区。每个图形按规则移动。", {"rule":"shape","groups":groups,"note":"按形状分成三组。"}))
    s2.append(scene("颜色不同仍是圆形", "红圆形和蓝圆形颜色不同，但它们形状相同，所以进入同一个圆形区域。", {"rule":"shape","groups":groups,"note":"颜色不同，不改变它们都是圆形这一点。"}))
    groups,layout=sort_groups(items,"color",layout)
    s2.append(scene("改按颜色分类", "现在换一条规则：按颜色分类。刚才在一起的图形，可能会分到不同区域。", {"rule":"color","groups":groups,"note":"换规则以后，同一批图形重新分组。"}))
    s2.append(scene("按颜色重新分组", "红色图形进入红色区，蓝色进入蓝色区，黄色进入黄色区。", {"rule":"color","groups":groups,"note":"现在只看颜色，形状先放在一边。"}))
    s2.append(scene("总结分类规则", "分类先要说清楚规则。按形状和按颜色，会得到不同的分组结果。", {"rule":"color","groups":groups,"note":"这是按照预设规则分类，不是机器学习训练。"}))
    lessons.append({"key":key,"file":"sorting-by-rule","stage":"PRIMARY_LOWER","title":title,"grades":"1—3 年级","kind":"sorting-by-rule","subject":SUBJECT,"objective":"理解先确定分类规则，再按照规则把物品分组。","summary":"同一组图形分别按形状、按颜色分类，观察规则如何改变分组。","knowledge_points":["分类规则","形状","颜色"],"data":{"items":items},"steps":s2})

    # PRIMARY_LOWER 3: instructions and route correction
    walls=[[1,1]]; goal=[0,4]; correct=["→","→","→","→"]; wrong=["↓","→","→"]
    good=move_robot(correct,walls,goal); bad=move_robot(wrong,walls,goal)
    robot_steps=[
        scene("认识方格地图", "机器人从左上角出发，终点在右上角。棕色格子是障碍，路线不能穿过去。", {"position":[0,0],"previous":[0,0],"path":[[0,0]],"commands":[],"current":-1,"status":"ready","walls":walls,"goal":goal,"note":"起点、终点和障碍都在五乘五地图上。"}),
        scene("写下箭头顺序", "每个箭头都表示地图上的方向。我们给机器人四个向右箭头，让它朝终点走。", {"position":[0,0],"previous":[0,0],"path":[[0,0]],"commands":correct,"current":0,"status":"ready","walls":walls,"goal":goal,"note":"顺序是：右、右、右、右。"}),
    ]
    for i, st in enumerate(good):
        robot_steps.append(scene("执行正确指令", f"第 {i+1} 个箭头亮起，机器人向右移动一格。它只执行这条指令。", st))
    robot_steps.append(scene("错误顺序会撞到障碍", "再看一条错误路线：先向下，再向右。第二条指令遇到障碍，机器人立即停下。", bad[-1]))
    fixed=good[-1].copy(); fixed["note"]="把路线改成：向右、向右、向右、向右。"
    robot_steps.append(scene("改正后到达终点", "把错误路线改为向右四次，再按顺序执行，就能到达终点。机器不会猜我们的想法。", fixed))
    lessons.append({"key":"primary-lower-robot-instructions","file":"robot-instructions","stage":"PRIMARY_LOWER","title":"箭头指令带机器人走到终点","grades":"1—3 年级","kind":"robot-instructions","subject":SUBJECT,"objective":"理解指令顺序会影响执行结果。","summary":"机器人按箭头逐格移动，遇到障碍会停止，并用改正后的顺序到达终点。","knowledge_points":["指令顺序","方向","障碍"],"data":{"walls":walls,"goal":goal,"correct":correct,"wrong":wrong},"steps":robot_steps})

    # PRIMARY_UPPER 4: pixels
    coarse,fine=pixel_data()
    pixel_steps=[]
    pixel_steps.append(scene("图片里有小方格", "一张简单图案可以拆成许多小单元。我们把每格当作一个像素，用行和列组成颜色矩阵，一格一格画出来。", {"matrix":fine,"coarse":coarse,"filled":0,"revealFrom":0,"note":"每格暂时都是空白，接下来逐格填色。"}))
    pixel_steps.append(scene("先用较粗网格", "先看四乘四的大格子。每一格记录一个颜色，逐格填出一个对称的小图案。格子的位置也很重要。", {"matrix":fine,"coarse":coarse,"filled":4,"revealFrom":0,"note":"前四个格子逐格着色。"}))
    pixel_steps.append(scene("继续填入颜色", "再填下一行的颜色。深色和浅色方格排在一起，图案轮廓慢慢出现。", {"matrix":fine,"coarse":coarse,"filled":8,"revealFrom":4,"note":"八个格子已有颜色，矩阵来自同一图案。"}))
    pixel_steps.append(scene("图案逐渐完成", "继续填完下面两行，四乘四的图案完成了。每个小格都对应一个颜色单元。", {"matrix":fine,"coarse":coarse,"filled":16,"revealFrom":8,"note":"四乘四共有 16 个颜色单元。"}))
    pixel_steps.append(scene("换成更细网格", "把同一图案放进八乘八网格，格子变小了。每个粗格现在对应四个更小的格子；图案本身没有换。", {"matrix":fine,"coarse":coarse,"filled":16,"note":"这是同一份 8×8 颜色矩阵，不是另一张图片。"}))
    pixel_steps.append(scene("观察局部细节", "放大一小块区域可以看到更多颜色格。细网格能记录更细的边缘变化，比如深色和浅色交界的位置。", {"matrix":fine,"coarse":coarse,"filled":16,"highlight":[1,1],"note":"局部格子更多，图案细节也能表示得更多。"}))
    pixel_steps.append(scene("比较记录的信息", "四乘四有十六格，八乘八有六十四格。若每格都要记录一种颜色，单元变多通常意味着要记录更多颜色选择；这不是显示器的物理大小。", {"matrix":fine,"coarse":coarse,"filled":16,"note":"这里只数单元；没有模拟压缩或显示器硬件。"}))
    pixel_steps.append(scene("总结像素和细节", "像素是图片中的小颜色单元。网格更细能表达更多局部变化，但不代表任何图片都一定更好。", {"matrix":fine,"coarse":coarse,"filled":16,"highlight":[2,2],"note":"像素数量、细节和信息量有关，图片效果还受其他因素影响。"}))
    lessons.append({"key":"primary-upper-pixels-build-picture","file":"pixels-build-picture","stage":"PRIMARY_UPPER","title":"小方格怎样组成一张图片","grades":"4—6 年级","kind":"pixels-build-picture","subject":SUBJECT,"objective":"理解图片可以由许多带颜色的小单元组成。","summary":"同一份颜色矩阵逐步填色，并对比四乘四与八乘八网格的细节和单元数量。","knowledge_points":["像素","颜色矩阵","图像细节"],"data":{"coarse":coarse,"matrix":fine},"steps":pixel_steps})

    # PRIMARY_UPPER 5: bubble sort computed comparison by comparison
    default=[5,2,4,1,3]
    comps, sorted_cards=bubble_states(default)
    bubble_steps=[scene("先看原始卡片", "卡片现在是 5、2、4、1、3。接下来只比较相邻两张，需要时才交换。", {"array":default,"left":None,"right":None,"note":"原始顺序：5、2、4、1、3。"})]
    for c in comps:
        bubble_steps.append(scene("比较相邻卡片", c["text"], {"array":[x["value"] for x in c["cards"]],"cards":c["cards"],"previousCards":c["previousCards"],"left":c["left"],"right":c["right"],"swap":c["swap"],"note":c["note"]}))
    bubble_steps.append(scene("数字排好了", "一轮轮比较后，卡片从小到大排成 1、2、3、4、5。交换时只改变相邻位置，数字没有改变。", {"array":[x["value"] for x in sorted_cards],"cards":sorted_cards,"left":None,"right":None,"note":"排序结果：[1, 2, 3, 4, 5]。"}))
    lessons.append({"key":"primary-upper-cards-bubble-sort","file":"cards-bubble-sort","stage":"PRIMARY_UPPER","title":"数字卡片怎样排整齐","grades":"4—6 年级","kind":"cards-bubble-sort","subject":SUBJECT,"objective":"理解比较相邻两项、必要时交换并重复比较的排序过程。","summary":"默认数组 [5, 2, 4, 1, 3] 由真实相邻比较和交换得到升序结果。","knowledge_points":["相邻比较","交换","冒泡排序"],"data":{"values":default,"sorted":[x["value"] for x in sorted_cards]},"steps":bubble_steps})

    # PRIMARY_UPPER 6: network packets
    message="明天图书馆见"; chunks=["明天","图书","馆见"]
    paths={"1":["S","A","C","T"],"2":["S","B","D","T"],"3":["S","A","D","T"]}
    arrival=["2","3","1"]
    packets=[]
    packet_steps=[scene("消息怎样送到", "发送设备要把一条消息交给另一台设备。中间的圆点代表连接节点，连线表示本例可经过的路线。画面是简化模型。", {"packets":[],"activeEdges":[],"note":"消息："+message})]
    packet_steps.append(scene("消息切成编号块", "这句短消息被切成三个编号信息块。编号像贴在包裹上的顺序标签；每块可以沿可用连接移动。", {"packets":[{"id":str(i+1),"chunk":chunk,"path":["S"],"status":"ready","order":i} for i,chunk in enumerate(chunks)],"activeEdges":[],"note":"三个块：01 明天；02 图书；03 馆见。"}))
    for order_i,pid in enumerate(arrival):
        packets.append({"id":pid,"chunk":chunks[int(pid)-1],"path":paths[pid],"status":"arrived","order":order_i})
        hot=[[paths[pid][i],paths[pid][i+1]] for i in range(len(paths[pid])-1)]
        packet_steps.append(scene("信息块到达接收端", f"编号 {pid} 的信息块这次先到达。它沿连接路线移动；目前收到顺序是“{'、'.join([p['id'] for p in packets])}”。", {"packets":packets[:],"movingId":pid,"activeEdges":hot,"note":"本例块 2、3、1 分别走连接路线；不表示每次传输都如此。"}))
    packet_steps.append(scene("根据编号重新排列", "接收端按 01、02、03 排好信息块。到达顺序是 02、03、01；编号仍告诉接收端原来的顺序。", {"packets":[dict(p,order=int(p["id"])-1) for p in packets],"activeEdges":[],"note":"编号顺序：01 → 02 → 03。"}))
    packet_steps.append(scene("完整消息出现", "信息块拼回“明天图书馆见”。这是本例的教学约定，不代表所有网络协议都保证可靠、有序。", {"packets":[dict(p,order=int(p["id"])-1) for p in packets],"activeEdges":[],"note":"重组结果："+message}))
    packet_steps.append(scene("总结发送到接收", "发送端分块，数据经过连接节点，接收端按照编号重组。本课没有发送真实消息，也没有连接网络。", {"packets":[dict(p,order=int(p["id"])-1) for p in packets],"activeEdges":[],"note":"发送 → 传输 → 接收 → 重组。"}))
    lessons.append({"key":"primary-upper-message-packets","file":"message-packets","stage":"PRIMARY_UPPER","title":"一条消息怎样通过网络送出去","grades":"4—6 年级","kind":"message-packets","subject":SUBJECT,"objective":"理解发送端、传输过程、接收端与分组传输的基本直觉。","summary":"模拟一条短消息分块、沿连接节点到达、按编号重组的过程。","knowledge_points":["发送与接收","信息块","编号重组"],"data":{"message":message,"chunks":chunks,"paths":paths,"arrival":arrival},"steps":packet_steps})

    # JUNIOR 7: linear search, with calculated found and missing paths
    array=[12,7,20,9,15,3]
    search_steps=[scene("从第一项开始找", "数组不要求排好序。目标是 9；线性查找从下标 0 开始，按顺序逐项比较。i 表示当前下标，检查过的项目不会跳回来。", {"array":array,"target":9,"current":None,"checked":[],"codeLine":0,"note":"i = 0；下标从 0 开始。"})]
    search_steps.extend(linear_steps(array,9,False))
    search_steps.extend(linear_steps(array,8,True))
    lessons.append({"key":"junior-linear-search","file":"linear-search","stage":"JUNIOR","title":"从一排数据中找到目标：线性查找","grades":"7—9 年级","kind":"linear-search","subject":SUBJECT,"objective":"理解线性查找按顺序检查数据，并区分位置和下标。","summary":"真实检查目标 9 和不存在的目标 8，显示比较位置、代码步骤和停止条件。","knowledge_points":["线性查找","数组下标","停止条件"],"data":{"array":array,"target":9,"missing":8},"steps":search_steps})

    # JUNIOR 8: stack and queue
    st=[]; q=[]; stack_out=[]; queue_out=[]; container_steps=[]
    container_steps.append(scene("同样放入 A、B、C", "我们用相同顺序 A、B、C 操作两个容器。一个是叠放的栈，一个是排队的队列。", {"focus":"stack","stack":[],"queue":[],"stackOut":[],"queueOut":[],"note":"同一输入顺序，取出规则不同。"}))
    st=["A","B","C"]
    container_steps.append(scene("盘子依次叠起来", "A、B、C 依次进入栈，C 在最上面。栈顶是取出的一端。", {"focus":"stack","stack":st[:],"queue":[],"stackOut":[],"queueOut":[],"note":"栈顶是 C；新项目也从栈顶加入。"}))
    stack_reason={"C":"C 最后放入，所以先取；A 和 B 还留在下面。","B":"C 离开后，B 成为新的栈顶；A 仍在下面。","A":"最后取出 A，栈回到空状态，栈顶也消失了。"}
    for val in ["C","B","A"]:
        st.pop();stack_out.append(val)
        container_steps.append(scene("从栈顶取出", f"现在从栈顶取出 {val}。{stack_reason[val]}", {"focus":"stack","stack":st[:],"queue":[],"stackOut":stack_out[:],"queueOut":[],"note":"栈的取出顺序：C、B、A。"}))
    container_steps.append(scene("空栈不能再取", "栈已经空了。再取一次没有项目可以拿，操作应当停止并说明容器为空。", {"focus":"stack","stack":[],"queue":[],"stackOut":stack_out[:],"queueOut":[],"note":"空栈没有栈顶，不能继续出栈。"}))
    q=["A","B","C"]
    container_steps.append(scene("同样顺序排进队列", "现在把 A、B、C 依次排进队列。新项目从队尾加入，最早的 A 在队首。", {"focus":"queue","stack":[],"queue":q[:],"stackOut":stack_out[:],"queueOut":[],"note":"队首在左，队尾在右。"}))
    queue_reason={"A":"A 离开后，B 成为新队首；B 仍比 C 更早到达。","B":"现在 B 离开，C 成为新队首；添加和移除发生在不同两端。","C":"最后 C 离开，队列也变空了。"}
    for val in ["A","B","C"]:
        q.pop(0);queue_out.append(val)
        container_steps.append(scene("从队首依次离开", f"现在队首的 {val} 离开。{queue_reason[val]}", {"focus":"queue","stack":[],"queue":q[:],"stackOut":stack_out[:],"queueOut":queue_out[:],"note":"队列取出顺序：A、B、C。"}))
    container_steps.append(scene("比较两种顺序", "栈使用入栈和出栈，出口都在栈顶；队列从队尾入队、从队首出队。相同的 A、B、C 输入，操作规则决定了不同的取出顺序。", {"focus":"queue","stack":[],"queue":[],"stackOut":stack_out[:],"queueOut":queue_out[:],"note":"栈：C、B、A；队列：A、B、C。"}))
    lessons.append({"key":"junior-stack-and-queue","file":"stack-and-queue","stage":"JUNIOR","title":"叠盘子和排队：栈与队列","grades":"7—9 年级","kind":"stack-and-queue","subject":SUBJECT,"objective":"理解后进先出与先进先出的区别。","summary":"用同样的 A、B、C 顺序真实展示栈顶与队首的取出次序和空栈边界。","knowledge_points":["栈","队列","先进先出","后进先出"],"data":{"items":["A","B","C"]},"steps":container_steps})

    # JUNIOR 9: independent training and testing examples, predictions calculated only from train
    train=[
        {"id":"R1","xy":[1.0,1.0],"label":"红"},{"id":"R2","xy":[1.6,1.4],"label":"红"},{"id":"R3","xy":[2.0,1.0],"label":"红"},
        {"id":"B1","xy":[4.0,3.5],"label":"蓝"},{"id":"B2","xy":[4.5,4.0],"label":"蓝"},{"id":"B3","xy":[4.0,4.5],"label":"蓝"},
    ]
    tests=[{"id":"T1","xy":[2.3,1.6],"truth":"红"},{"id":"T2","xy":[3.4,3.1],"truth":"蓝"},{"id":"T3","xy":[2.7,2.8],"truth":"红"}]
    test_steps=[scene("先把样例分开", "下面是一组很小的合成二维数据，每个点有两个数值特征。红点和蓝点作为训练样例，另有三个测试点。", {"train":train,"phase":"train","note":"测试点的真实类别还没有参与规则计算。"})]
    test_steps.append(scene("训练阶段建立规则", "这里使用最近邻规则。比较新点到训练点的距离，找最近的一点，再借用它的类别。本例按两个坐标差的平方和比较，数值更小表示更近。", {"train":train,"phase":"train","note":"判断规则只读取训练坐标和训练类别。"}))
    for t in tests:
        p=nearest(t["xy"],train)
        test_steps.append(scene("先预测测试点", f"只看测试点 {t['id']} 的位置，连接到最近训练点 {p['id']}，直线距离约 {p['distance']:.2f}。最近点属于{p['label']}类，所以先预测{p['label']}色。", {"train":train,"test":{"id":t["id"],"xy":t["xy"]},"nearest":p,"phase":"test","prediction":p["label"],"note":"先按训练样例预测；还没有揭开真实类别。"}))
        good=p["label"]==t["truth"]
        test_steps.append(scene("揭开真实类别", f"测试点 {t['id']} 的真实类别是{t['truth']}色，刚才预测{'相同' if good else '不同'}。这一步才把测试标签揭开，并按实际比较累计正确数量。", {"train":train,"test":{"id":t["id"],"xy":t["xy"]},"nearest":p,"phase":"test","prediction":p["label"],"truth":t["truth"],"correct":good,"note":"预测与真实类别比较后才记下结果。"}))
    correct=sum(1 for t in tests if nearest(t["xy"],train)["label"]==t["truth"])
    test_steps.append(scene("查看实际评估数量", f"三个测试点中，这条简单规则判断对了 {correct} 个。这个数字只属于本组合成测试样例。", {"train":train,"phase":"summary","correct":correct,"total":len(tests),"note":f"本次测试：{correct} / {len(tests)}。"}))
    test_steps.append(scene("记住与判断新样例", "训练样例帮助建立规则；测试样例用来检查它遇到新位置时的表现。评估样例不参与本次训练或选规则。", {"train":train,"phase":"summary","correct":correct,"total":len(tests),"note":"这是小型合成数据和简化最近邻模型，不代表大型 AI。"}))
    lessons.append({"key":"junior-training-and-testing","file":"training-and-testing","stage":"JUNIOR","title":"为什么学习样例和检查样例要分开","grades":"7—9 年级","kind":"training-and-testing","subject":SUBJECT,"objective":"理解训练数据与测试数据承担不同作用。","summary":"用训练点建立最近邻分类，再预测并揭示独立测试点的真实类别。","knowledge_points":["训练数据","测试数据","最近邻","评估"],"data":{"train":train,"tests":tests,"correct":correct},"steps":test_steps})

    # SENIOR 10: Dijkstra on six nodes, with disconnected F as boundary
    nodes=["A","B","C","D","E","F"]
    edges=[["A","B",4],["A","C",2],["C","B",1],["B","D",5],["C","D",8],["C","E",10],["D","E",2]]
    dij=dijkstra(nodes,edges,"A")
    main_steps=[scene("用带权图表示路线", "节点表示地点，边表示可以走的连接；边上的非负数字是同一单位的路程成本。目标从 A 到 E。路线要比较总成本，不能只数经过几条边。", {"distances":{"A":0,"B":None,"C":None,"D":None,"E":None,"F":None},"settled":[],"selected":None,"routeEdges":[],"relaxed":[],"note":"F 没有连接，留作不可达边界例子。"})]
    main_steps.append(scene("先初始化候选距离", "从 A 出发，A 的距离是 0；其他节点暂时记为无穷大，表示目前还没有找到路线。每轮选待检查距离最小的节点；同距离按字母顺序稳定选择。", {"distances":{"A":0,"B":None,"C":None,"D":None,"E":None,"F":None},"settled":[],"selected":"A","routeEdges":[],"relaxed":[],"note":"待检查节点中，先选当前距离最小的节点。"}))
    for event in dij["events"]:
        relax=event["relaxations"]
        details=[]
        relaxed=[]
        for r in relax:
            if r["old"] is None:
                details.append(f"{r['from']} 到 {r['to']}：0 + {r['weight']} = {r['candidate']}，首次到达")
            else:
                details.append(f"{r['from']} 到 {r['to']}：{r['base']} + {r['weight']} = {r['candidate']}，原候选 {r['old']}，{'更新' if r['updated'] else '保留较短值'}")
            if r["updated"]:
                relaxed.append(r["from"]+r["to"])
        txt=f"选中 {event['selected']}，因为它是未确定节点里当前距离最小的。边权非负时，这个最小距离已经可以确定。更短的候选会把当前节点记作前驱，否则保留原距离。" + "；".join(details) + "。"
        ds={k:(None if not math.isfinite(v) else v) for k,v in event["dist"].items()}
        main_steps.append(scene("选点并检查相邻边",txt,{"distances":ds,"settled":event["settled"],"selected":event["selected"],"routeEdges":[],"relaxed":relaxed,"note":"新候选 = 当前距离 + 边权；更短才更新距离和前驱。"}))
    path=path_to(dij["prev"],"A","E"); cost=dij["dist"]["E"]
    routeEdges=[path[i]+path[i+1] for i in range(len(path)-1)]
    main_steps.append(scene("得到最短路径", f"从 A 到 E 的前驱链还原为 {' → '.join(path)}，成本相加为 2 + 1 + 5 + 2 = {cost}。边数较少不一定总成本较小。", {"distances":{"A":0,"B":3,"C":2,"D":8,"E":10,"F":None},"settled":dij["settled"],"selected":"E","routeEdges":routeEdges,"relaxed":[],"note":f"最短路径：{' → '.join(path)}；总成本 {cost}。"}))
    main_steps.append(scene("检查不可达节点", "节点 F 没有连到图中其他节点，距离仍为无穷大。算法不会编造一条到 F 的路线。", {"distances":{"A":0,"B":3,"C":2,"D":8,"E":10,"F":None},"settled":dij["settled"],"selected":"F","routeEdges":routeEdges,"relaxed":[],"note":"F 不可达；Dijkstra 需要边权非负。"}))
    main_steps.append(scene("总结距离更新", "每次确定当前最小的候选距离，再用相邻边尝试缩短其他距离。这里的图很小，不是完整地图导航系统。", {"distances":{"A":0,"B":3,"C":2,"D":8,"E":10,"F":None},"settled":dij["settled"],"selected":"E","routeEdges":routeEdges,"relaxed":[],"note":"非负边权、候选距离、前驱更新，共同得到路线。"}))
    lessons.append({"key":"senior-shortest-path","file":"shortest-path","stage":"SENIOR","title":"怎样找到总路程最短的路线","grades":"10—12 年级","kind":"shortest-path","subject":SUBJECT,"objective":"理解图、边权、候选距离与最短路径更新。","summary":f"对六节点非负带权图实际执行 Dijkstra，得到 A 到 E 的路径成本 {cost}，并检查不可达节点 F。","knowledge_points":["带权图","Dijkstra 算法","候选距离","前驱"],"data":{"nodes":nodes,"edges":edges,"start":"A","end":"E","distance":cost,"path":path,"unreachable":"F"},"steps":main_steps})

    # SENIOR 11: gradient descent and large-step counterexample
    alpha=.15; xs=4.0; goodpoints=[{"x":xs,"y":xs*xs,"direction":"向左"}]
    for _ in range(6):
        xs=xs-alpha*2*xs;goodpoints.append({"x":xs,"y":xs*xs,"direction":"向左" if xs>=0 else "向右"})
    grad_steps=[scene("观察目标函数", "目标是让 f(x)=x² 变小。横轴表示 x，纵轴表示函数值；曲线最低点在 x 等于 0。每次更新都希望找到一个函数值更小的位置。", {"points":[],"current":{"x":4,"y":16,"direction":"向左"},"iteration":0,"note":"初始位置 x₀=4，函数值 f(4)=16。"})]
    grad_steps.append(scene("说明变化方向", "在 x=4 时，导数 2x 的值是 8，表示曲线向右上升。要往低处走，点应沿斜率相反的方向向左移动。", {"points":[goodpoints[0]],"current":goodpoints[0],"iteration":0,"note":"斜率为 2x；更新方向取斜率的相反方向。"}))
    for i,pt in enumerate(goodpoints[1:],1):
        prev=goodpoints[i-1]
        grad_steps.append(scene("按公式更新位置", f"第 {i} 次：x 从 {prev['x']:.4f} 更新到 {pt['x']:.4f}，函数值从 {prev['y']:.4f} 变为 {pt['y']:.4f}。这里 α=0.15，导数 2x 决定方向。", {"points":goodpoints[:i+1],"current":pt,"iteration":i,"note":"x_next = x − 0.15 × 2x；位置和函数值都由公式计算。"}))
    large=1.1; badx=4.0; badpts=[{"x":badx,"y":badx*badx,"direction":"向左"}]
    for i in range(3):
        badx=badx-large*2*badx;badpts.append({"x":badx,"y":badx*badx,"direction":"向右越过最低点" if i==0 else ("向左" if badx>0 else "向右")})
        prev=badpts[-2];pt=badpts[-1]
        grad_steps.append(scene("对照较大的步长", f"步长改成 1.10。第 {i+1} 次从 x={prev['x']:.3f} 到 x={pt['x']:.3f}，函数值变为 {pt['y']:.3f}。点越过 0 后反向更新，数值开始远离最低点。", {"points":badpts[:],"current":pt,"iteration":i+1,"note":"x_next = x − 1.10 × 2x；本例越过最低点且函数值增大。"}))
    grad_steps.append(scene("比较方向和步长", "小步长让这个例子逐渐靠近最低点；较大步长越过最低点并让函数值增大。不同函数和步长的结果可能不同。", {"points":badpts,"current":badpts[-1],"iteration":3,"note":"方向与步长都会影响更新；本例不代表所有函数的收敛保证。"}))
    lessons.append({"key":"senior-gradient-descent","file":"gradient-descent","stage":"SENIOR","title":"梯度下降怎样一步步靠近最低点","grades":"10—12 年级","kind":"gradient-descent","subject":SUBJECT,"objective":"建立目标函数、当前点、变化方向和学习步长的直观联系。","summary":"按 x_next=x−α×2x 计算 f(x)=x² 的更新，并对照实际计算出的过大步长轨迹。","knowledge_points":["目标函数","导数方向","学习步长","梯度下降"],"data":{"function":"x²","x0":4,"alpha":0.15,"largeAlpha":1.1,"updates":6},"steps":grad_steps})

    # SENIOR 12: every synthetic sample checked at both thresholds, actual counts and metrics computed
    records=[
        {"id":"M1","truth":"spam","score":0.90},{"id":"M2","truth":"normal","score":0.80},
        {"id":"M3","truth":"spam","score":0.70},{"id":"M4","truth":"normal","score":0.60},
        {"id":"M5","truth":"spam","score":0.55},{"id":"M6","truth":"spam","score":0.40},
        {"id":"M7","truth":"normal","score":0.30},{"id":"M8","truth":"normal","score":0.10},
    ]
    met_steps=[scene("先区分真实和预测", "正类是垃圾邮件，负类是正常邮件。真实类别来自合成标签；预测类别由模拟分数和阈值决定。", {"counts":{"tp":0,"fp":0,"fn":0,"tn":0},"threshold":0.5,"currentId":"—","note":"分数是教学模拟值，不是实际模型输出。"})]
    first=metrics(records,.5)
    met_steps.append(scene("设置阈值 0.50", "规则是分数大于等于阈值就预测为垃圾邮件。先用 0.50，逐条检查八个合成编号。", {"counts":{"tp":0,"fp":0,"fn":0,"tn":0},"threshold":.5,"currentId":"准备开始","note":"预测规则：分数 ≥ 0.50 判为垃圾邮件。"}))
    for event in first["events"]:
        truth="垃圾邮件" if event["truth"]=="spam" else "正常邮件"
        pred="垃圾邮件" if event["predicted"]=="spam" else "正常邮件"
        kind_text={"tp":"真正例：垃圾邮件被正确识别。","fp":"假正例：正常邮件被误报为垃圾邮件。","fn":"假负例：垃圾邮件被漏报为正常邮件。","tn":"真负例：正常邮件被正确放行。"}[event["bucket"]]
        met_steps.append(scene("判断一个合成样例", f"编号 {event['id']} 的真实类别是{truth}，模拟分数 {event['score']:.2f}。按 0.50 阈值预测为{pred}，归入{kind_text}", {"counts":event["counts"],"threshold":.5,"currentId":event["id"],"current":{"id":event["id"],"truth":event["truth"],"predicted":event["predicted"],"bucket":event["bucket"],"score":event["score"]},"note":kind_text}))
    met_steps.append(scene("由计数计算三项指标", "准确率看全部样例判断正确的比例；精确率看被报为垃圾邮件的有多少是真的；召回率看垃圾邮件里找回多少。", {"counts":first["counts"],"threshold":.5,"currentId":"8 条已检查","metrics":{"accuracy":first["accuracy"],"precision":first["precision"],"recall":first["recall"]},"note":"指标根据当前四类计数计算。"}))
    met_steps.append(scene("改用阈值 0.65", "现在把阈值提高到 0.65。仍按同一批编号逐个判断；真实标签没有用于选择这个阈值。", {"counts":{"tp":0,"fp":0,"fn":0,"tn":0},"threshold":.65,"currentId":"准备重新检查","note":"同一规则，阈值变化；重新从 0 计数。"}))
    second=metrics(records,.65)
    for event in second["events"]:
        truth="垃圾邮件" if event["truth"]=="spam" else "正常邮件"
        pred="垃圾邮件" if event["predicted"]=="spam" else "正常邮件"
        kind_text={"tp":"真正例：垃圾邮件被正确识别。","fp":"假正例：正常邮件被误报为垃圾邮件。","fn":"假负例：垃圾邮件被漏报为正常邮件。","tn":"真负例：正常邮件被正确放行。"}[event["bucket"]]
        met_steps.append(scene("重新判断一个样例", f"编号 {event['id']} 的真实类别是{truth}，模拟分数 {event['score']:.2f}。按 0.65 阈值预测为{pred}，归入{kind_text}", {"counts":event["counts"],"threshold":.65,"currentId":event["id"],"current":{"id":event["id"],"truth":event["truth"],"predicted":event["predicted"],"bucket":event["bucket"],"score":event["score"]},"note":kind_text}))
    met_steps.append(scene("比较两个阈值", "0.50 得到 TP3、FP2、FN1、TN2；0.65 得到 TP2、FP1、FN2、TN3。两组准确率都由计数得到。", {"counts":second["counts"],"threshold":.65,"currentId":"0.50 与 0.65","metrics":{"accuracy":second["accuracy"],"precision":second["precision"],"recall":second["recall"]},"compare":{"first":first["counts"],"second":second["counts"],"firstMetrics":{"accuracy":first["accuracy"],"precision":first["precision"],"recall":first["recall"]},"secondMetrics":{"accuracy":second["accuracy"],"precision":second["precision"],"recall":second["recall"]}},"note":"误报减少，同时漏报增加；不能只看一个指标。"}))
    met_steps.append(scene("理解错误和指标", "提高阈值后，这组数据的误报变少，漏报变多。准确率没有变化；不同场景要关注不同错误影响。", {"counts":second["counts"],"threshold":.65,"currentId":"总结","metrics":{"accuracy":second["accuracy"],"precision":second["precision"],"recall":second["recall"]},"compare":{"first":first["counts"],"second":second["counts"],"firstMetrics":{"accuracy":first["accuracy"],"precision":first["precision"],"recall":first["recall"]},"secondMetrics":{"accuracy":second["accuracy"],"precision":second["precision"],"recall":second["recall"]}},"note":"合成样例演示指标含义，不表示真实邮件模型性能。"}))
    lessons.append({"key":"senior-classification-metrics","file":"classification-metrics","stage":"SENIOR","title":"分类模型的误报与漏报","grades":"10—12 年级","kind":"classification-metrics","subject":SUBJECT,"objective":"理解真正例、假正例、假负例、真负例及常用指标。","summary":"用八个合成编号样例分别计算 0.50 与 0.65 阈值下的混淆矩阵、准确率、精确率与召回率。","knowledge_points":["混淆矩阵","准确率","精确率","召回率","阈值"],"data":{"records":records,"thresholds":[.5,.65],"expected":{"0.5":first["counts"],"0.65":second["counts"]}},"steps":met_steps})

    # Consistent scene ids are assigned only after every algorithm has produced its states.
    for lesson in lessons:
        for i, st in enumerate(lesson["steps"], 1):
            st["id"] = f"scene-{i:02d}"
    return lessons


def cover_svg(lesson):
    palette={"PRIMARY_LOWER":("#e7f1e9","#326c59"),"PRIMARY_UPPER":("#e7eef6","#416a93"),"JUNIOR":("#eee9f6","#69568a"),"SENIOR":("#f5ece0","#915c37")}
    bg,accent=palette[lesson["stage"]]
    words=[lesson["title"][i:i+15] for i in range(0,len(lesson["title"]),15)][:2]
    title="".join(f'<tspan x="64" dy="{0 if i==0 else 46}">{esc(x)}</tspan>' for i,x in enumerate(words))
    kind=lesson["kind"]
    art=''
    if kind in ("input-process-output","sorting-by-rule"):
        art='<circle cx="660" cy="210" r="58" fill="#d66b61"/><path d="M770 160 830 260H710Z" fill="#d8ae4c" stroke="#263c4e" stroke-width="5"/><rect x="650" y="310" width="120" height="100" rx="8" fill="#6c8db2"/><path d="M560 260H680M840 260H890" stroke="#53677d" stroke-width="9" marker-end="url(#a)"/>'
    elif kind=="robot-instructions":
        art=''.join(f'<rect x="{580+c*58}" y="{118+r*58}" width="50" height="50" rx="5" fill="{"#9db2c4" if (r,c)==(1,1) else "#fff"}" stroke="#607184" stroke-width="3"/>' for r in range(4) for c in range(4))+'<circle cx="610" cy="150" r="20" fill="#dfad52"/><path d="M640 150h145" stroke="#326c59" stroke-width="7" marker-end="url(#a)"/>'
    elif kind in ("pixels-build-picture","cards-bubble-sort"):
        art=''.join(f'<rect x="{580+c*58}" y="{128+r*58}" width="54" height="54" fill="{"#24384b" if (r+c)%3 else "#d88960"}" stroke="#fff" stroke-width="4"/>' for r in range(4) for c in range(4))
    elif kind in ("message-packets","shortest-path"):
        art='<path d="M560 200 660 130 750 205 850 130M560 200 660 300 750 205 850 300" fill="none" stroke="#6686a4" stroke-width="8"/><circle cx="560" cy="200" r="24" fill="#d66b61"/><circle cx="660" cy="130" r="24" fill="#88a989"/><circle cx="660" cy="300" r="24" fill="#d8ae4c"/><circle cx="750" cy="205" r="24" fill="#9b89b8"/><circle cx="850" cy="130" r="24" fill="#416a93"/>'
    elif kind in ("linear-search","classification-metrics"):
        art=''.join(f'<rect x="{555+c*78}" y="{170+r*78}" width="68" height="68" rx="9" fill="{["#e5b968","#d77c6c","#84a890","#8d99b0"][(r*2+c)%4]}" stroke="#fff" stroke-width="4"/>' for r in range(2) for c in range(2))
    elif kind in ("stack-and-queue","training-and-testing"):
        art='<rect x="575" y="285" width="115" height="48" rx="10" fill="#6c8db2"/><rect x="575" y="229" width="115" height="48" rx="10" fill="#d8ae4c"/><rect x="575" y="173" width="115" height="48" rx="10" fill="#d66b61"/><circle cx="790" cy="190" r="22" fill="#d66b61"/><rect x="765" y="260" width="48" height="48" fill="#6c8db2"/><path d="M700 350H860" stroke="#61758a" stroke-width="8" marker-end="url(#a)"/>'
    else:
        art='<path d="M565 365 Q690 110 850 365" fill="none" stroke="#416a93" stroke-width="9"/><circle cx="650" cy="255" r="12" fill="#d66b61"/><circle cx="720" cy="185" r="12" fill="#d66b61"/><circle cx="780" cy="245" r="12" fill="#d66b61"/>'
    stage=STAGES[lesson["stage"]][0]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-label="{esc(lesson['title'])}课件封面"><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 10 5 0 10Z" fill="{accent}"/></marker></defs><rect width="960" height="540" rx="28" fill="{bg}"/><rect x="0" y="0" width="28" height="540" fill="{accent}"/><text x="64" y="94" font-size="22" font-family="sans-serif" fill="{accent}">{stage} · {lesson['grades']}</text><text x="64" y="190" font-size="40" font-weight="700" font-family="sans-serif" fill="#26374b">{title}</text><text x="64" y="335" font-size="22" font-family="sans-serif" fill="#47576a">{esc(lesson['objective'])}</text>{art}<text x="64" y="492" font-size="18" font-family="sans-serif" fill="#67788a">霜铃 K12 教学动画 · 自动演示与可选实践</text></svg>'''


def esc(value):
    return str(value).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")


STYLE = r'''*{box-sizing:border-box}html{color-scheme:light}body{margin:0;background:#f2f4f3;color:#26364a;font:17px/1.55 system-ui,-apple-system,"Noto Sans CJK SC","Microsoft YaHei",sans-serif}button,select,input{font:inherit;color:inherit}button{min-height:46px;padding:9px 16px;border:1px solid #bdc9cf;border-radius:12px;background:#fff;cursor:pointer}button:hover{background:#f1f5f5}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #237e72;outline-offset:2px}button:disabled{opacity:.55;cursor:not-allowed}.primary{background:#256e62;border-color:#256e62;color:#fff;font-weight:700}.primary:hover{background:#19584e}.shell{max-width:1440px;margin:0 auto;padding:18px 20px 32px}.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px}.brand{min-width:0}.brand h1{font-size:clamp(20px,2.2vw,29px);line-height:1.22;margin:0 0 5px}.meta{display:flex;flex-wrap:wrap;gap:9px 18px;color:#596a7b;font-size:15px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;align-items:start}.viewer,.lesson-side,.practice-panel{border:1px solid #d4dedd;border-radius:18px;background:#fff;box-shadow:0 5px 18px #1f35400c}.viewer{overflow:hidden}.scene-meta{padding:11px 16px;border-bottom:1px solid #e2e8e7;color:#526579;font-size:14px}.canvas{display:grid;place-items:center;padding:8px 10px 2px;min-height:250px;background:#fbfcfa}.lesson-svg{display:block;width:100%;height:auto;max-height:55vh;min-height:245px;font-family:system-ui,-apple-system,"Noto Sans CJK SC","Microsoft YaHei",sans-serif}.lesson-svg text{fill:#26384b;font-size:22px}.lesson-svg .small-label{font-size:17px;fill:#526579}.lesson-svg .tiny-label{font-size:14px;fill:#526579}.lesson-svg .zone{fill:#f7f9f8;stroke:#d4dfdf;stroke-width:2}.lesson-svg .zone.active{fill:#eef7f4;stroke:#328273;stroke-width:4}.lesson-svg .zone-title,.lesson-svg .section-title{font-size:23px;font-weight:700}.lesson-svg .device-body{fill:#344b5c;stroke:#26384b;stroke-width:4}.lesson-svg .device-title,.lesson-svg .rule-text{fill:#fff}.lesson-svg .device-title{font-size:22px;font-weight:700}.lesson-svg .rule-text{font-size:17px}.lesson-svg .input-box{fill:#fff0dc;stroke:#d3a157;stroke-width:3}.lesson-svg .flow-line,.lesson-svg .axis,.lesson-svg .pointer-line{stroke:#61758a;stroke-width:4}.lesson-svg .packet{fill:#e5a64e;stroke:#8e5d26;stroke-width:3}.lesson-svg .token-letter{font-size:19px;font-weight:800;fill:#26384b}.lesson-svg .lamp-shell{fill:#ebefee;stroke:#61758a;stroke-width:4}.lesson-svg .lamp.lit .lamp-shell{fill:#ffebad;stroke:#c58829}.lesson-svg .lamp-base{fill:#9aa8aa}.lesson-svg .output-light{fill:#f3bf48;stroke:#8c631c;stroke-width:3}.lesson-svg .grid-cell{fill:#fff;stroke:#9cabb5;stroke-width:2}.lesson-svg .wall-cell{stroke:#927d66;stroke-width:2}.lesson-svg .map-label{font-size:14px;font-weight:700}.lesson-svg .trail-dot{fill:#78a28b}.lesson-svg .robot-face{fill:#e0ad54;stroke:#654c24;stroke-width:3}.lesson-svg .robot-letter{font-size:18px;font-weight:800;fill:#26384b}.lesson-svg .instruction{fill:#fff;stroke:#bdc9cf;stroke-width:2}.lesson-svg .instruction.active{fill:#fae4b1;stroke:#a87224;stroke-width:4}.lesson-svg .arrow-command{font-size:32px;font-weight:800}.lesson-svg .result-text{font-size:19px;font-weight:700}.lesson-svg .pixel-cell{stroke:#72808c;stroke-width:2}.lesson-svg .focus-outline{fill:none;stroke:#cc794b;stroke-width:6}.lesson-svg .info-strip{fill:#eef3f2;stroke:#d6e0df;stroke-width:1}.lesson-svg .number-card{fill:#fff;stroke:#9eacb6;stroke-width:3}.lesson-svg .number-card.compare{fill:#ffefc3;stroke:#c17e25;stroke-width:5}.lesson-svg .number-value{font-size:45px;font-weight:800}.lesson-svg .compare-line{stroke:#61758a;stroke-width:4}.lesson-svg .network-edge{stroke:#a6b5bf;stroke-width:7}.lesson-svg .network-edge.hot{stroke:#c78736;stroke-width:10}.lesson-svg .network-node{fill:#fff;stroke:#788c9d;stroke-width:4}.lesson-svg .network-node.endpoint{fill:#e7f0e9;stroke:#52836d}.lesson-svg .node-label,.lesson-svg .weight-label{font-size:17px;font-weight:700}.lesson-svg .packet-box{fill:#fff0ce;stroke:#bd8030;stroke-width:3}.lesson-svg .packet-label{font-size:16px;font-weight:700}.lesson-svg .search-cell{fill:#fff;stroke:#9eacb6;stroke-width:3}.lesson-svg .search-checked{fill:#e9f0ed;stroke:#83a18e;stroke-width:3}.lesson-svg .search-current{fill:#ffefc3;stroke:#c17e25;stroke-width:5}.lesson-svg .code-row{fill:#f4f6f7}.lesson-svg .code-active{fill:#deeee8;stroke:#65a18e;stroke-width:2}.lesson-svg .code-text{font-size:15px;font-family:ui-monospace,monospace}.lesson-svg .axis-tick{stroke:#61758a;stroke-width:2}.lesson-svg .container-item{fill:#eef2f4;stroke:#778b9b;stroke-width:2}.lesson-svg .container-item.top-item{fill:#ffefc3;stroke:#c17e25;stroke-width:4}.lesson-svg .item-letter{font-size:29px;font-weight:800}.lesson-svg .point-red{fill:#d66b61;stroke:#743d3a;stroke-width:3}.lesson-svg .point-blue{fill:#6c8db2;stroke:#314d68;stroke-width:3}.lesson-svg .point-test{fill:#e6b44f;stroke:#624816;stroke-width:3}.lesson-svg .nearest-line{stroke:#374b60;stroke-width:3;stroke-dasharray:8 7}.lesson-svg .graph-edge{stroke:#8da0af;stroke-width:6}.lesson-svg .graph-edge.active{stroke:#d09441;stroke-width:9}.lesson-svg .graph-edge.route{stroke:#43856c;stroke-width:10}.lesson-svg .weight-chip{fill:#fff;stroke:#c5d0d5;stroke-width:1}.lesson-svg .graph-node{fill:#edf2f5;stroke:#678094;stroke-width:4}.lesson-svg .graph-node.selected{fill:#f8e5b8;stroke:#b57b2c;stroke-width:6}.lesson-svg .curve{fill:none;stroke:#4c8291;stroke-width:6}.lesson-svg .descent-line{stroke:#cf8650;stroke-width:4;stroke-dasharray:7 5}.lesson-svg .descent-point{fill:#d66b61;stroke:#713d37;stroke-width:3}.lesson-svg .metric-cell{stroke:#fff;stroke-width:4}.lesson-svg .metric-title{font-size:19px;font-weight:700}.lesson-svg .metric-count{font-size:32px;font-weight:800}.lesson-svg .metric-summary{fill:#eef3f2;stroke:#cbd8d7;stroke-width:2}.lesson-svg .axis{stroke:#526579;stroke-width:3}.caption-area{padding:15px 18px 17px;border-top:1px solid #e5eae9;min-height:106px}.caption-area h2{font-size:15px;color:#596b7d;margin:0 0 5px}.caption-area p{font-size:18px;line-height:1.55;margin:0}.controls{display:flex;flex-wrap:wrap;gap:8px;padding:12px 15px 15px;border-top:1px solid #e5eae9}.controls button{flex:1 1 auto}.play-status{padding:0 16px 12px;color:#516577;font-size:14px}.lesson-side{padding:17px}.lesson-side h2{font-size:17px;margin:0 0 9px}.lesson-side p{margin:0 0 15px;color:#526579}.side-rule{border-top:1px solid #e2e8e7;padding-top:13px;margin-top:14px}.side-rule button{width:100%}.advanced{margin-top:12px;border-top:1px solid #e2e8e7;padding-top:11px}.advanced summary{cursor:pointer;font-weight:650}.advanced label,.practice-controls label{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:15px}.advanced select,.practice-controls select,.practice-controls input{min-width:0;min-height:44px;padding:7px 9px;border:1px solid #bdc9cf;border-radius:9px;background:#fff}.practice-panel{margin-top:14px;padding:16px}.practice-panel h2{margin:0 0 4px;font-size:20px}.practice-panel p{margin:5px 0 12px;color:#526579}.practice-controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px}.practice-controls button{min-height:44px}.practice-controls input{width:150px}.practice-error{color:#a1382d!important;font-weight:650;min-height:1.4em}.practice-output{padding:10px 12px;border-radius:10px;background:#eef3f2;font-weight:650}.practice-visual{margin-top:10px;border:1px solid #dfe7e6;border-radius:12px;overflow:hidden}.practice-visual .lesson-svg{min-height:190px;max-height:350px}.finish{padding:16px;border-top:1px solid #e5eae9;background:#f7faf9}.finish strong{display:block;margin-bottom:10px}.finish button{margin-right:8px}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.embedded .top,.embedded .lesson-side,.embedded #player-controls,.embedded #play-status,.embedded #current-step{display:none}.embedded .layout{display:block}.embedded .viewer{border:0;box-shadow:none}.embedded .caption-area{display:block}.is-paused .lesson-svg animateTransform,.is-paused .lesson-svg animateMotion{animation-play-state:paused}@media(max-width:850px){.layout{grid-template-columns:1fr}.lesson-side{order:2}.top{align-items:flex-start}.lesson-svg{max-height:54vh}.lesson-side{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}.lesson-side h2,.lesson-side>p{grid-column:1/-1}.side-rule{margin:0}.advanced{grid-column:1/-1}}@media(max-width:520px){body{font-size:16px}.shell{padding:10px 10px 24px}.top{display:block;margin-bottom:9px}.brand h1{font-size:22px}.meta{font-size:14px;gap:4px 12px}.layout{gap:10px}.viewer,.lesson-side,.practice-panel{border-radius:14px}.scene-meta{padding:8px 10px;font-size:13px}.canvas{padding:0 3px;min-height:205px}.lesson-svg{min-height:205px;max-height:42vh}.caption-area{padding:10px 12px;min-height:104px}.caption-area p{font-size:17px}.controls{padding:9px;gap:6px}.controls button{flex:1 1 42%;padding:8px 9px}.play-status{padding:0 12px 9px}.lesson-side{display:block;padding:13px}.side-rule{margin-top:10px;padding-top:10px}.practice-panel{padding:12px}.practice-controls input{width:120px}.lesson-svg .tiny-label{font-size:16px}}body{padding-bottom:66px}.controls{position:fixed;left:0;right:0;bottom:0;z-index:20;display:flex;justify-content:center;gap:8px;padding:8px 14px calc(8px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid #d4dedd;box-shadow:0 -4px 14px #1f354012}.controls button{flex:0 1 190px}body:not(.autoplay-active) #player-controls{display:none}@media(min-width:521px) and (max-height:800px){.lesson-svg{max-height:45vh;min-height:220px}}@keyframes pixel-in{from{opacity:.25;transform:scale(.25)}to{opacity:1;transform:scale(1)}}.lesson-svg .pixel-reveal{transform-box:fill-box;transform-origin:center;animation:pixel-in .42s ease-out var(--delay,0ms) both}.embedded .controls{display:none}@media(max-width:520px){.lesson-svg.mobile-svg{min-height:205px;max-height:42vh}.lesson-svg.mobile-svg text{font-size:19px}.lesson-svg.mobile-svg .small-label{font-size:17px}.lesson-svg.mobile-svg .tiny-label{font-size:16px}body{padding-bottom:62px}.controls{position:fixed;left:0;right:0;bottom:0;z-index:20;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:3px;padding:5px 4px calc(5px + env(safe-area-inset-bottom));background:#fff;box-shadow:0 -4px 14px #21354a18}.controls button{flex:initial;min-width:0;padding:4px 2px;font-size:14px;line-height:1.1;min-height:46px;white-space:normal}.top .primary{margin-top:8px;min-width:140px}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}'''


EMBED_STYLE = (SOURCE / "embedded.css").read_text(encoding="utf-8")

def html_document(lesson):
    definition={"key":lesson["key"],"title":lesson["title"],"stage":lesson["stage"],"stageName":STAGES[lesson["stage"]][0],"gradeRange":lesson["grades"],"kind":lesson["kind"],"objective":lesson["objective"],"data":lesson["data"],"steps":lesson["steps"]}
    json_data=json.dumps(definition,ensure_ascii=False,separators=(",",":" )).replace("</","<\\/")
    title=esc(lesson["title"]); stage=STAGES[lesson["stage"]][0]
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f2f4f3"><title>{title} · 霜铃 K12</title><style>{STYLE}{EMBED_STYLE}</style></head><body><main class="shell"><header class="top"><div class="brand"><h1>{title}</h1><div class="meta"><span>{stage} · {lesson['grades']}</span><span>学习目标：{esc(lesson['objective'])}</span></div></div><button class="primary" id="begin" type="button">开始播放</button></header><div class="layout"><section class="viewer" aria-label="教学动画"><div class="scene-meta" id="current-step"></div><div class="canvas" id="visual"></div><div class="caption-area"><h2>本段讲解字幕</h2><p id="caption" aria-live="polite"></p></div><div class="play-status" id="play-status" role="status" aria-live="polite"></div><div class="controls" id="player-controls"><button id="pause" type="button" disabled>暂停</button><button id="replay" type="button" disabled>重播本段</button><button id="restart" type="button" disabled>从头播放</button><button id="practice-toggle" type="button">自己试一试</button></div><div class="finish" id="finished" hidden><strong>播放完了。可以再看一遍，或自己试一试。</strong><button class="primary" id="again" type="button">再看一遍</button><button id="try-after" type="button">自己试一试</button></div></section><aside class="lesson-side"><h2>这一课观察什么</h2><p>{esc(lesson['objective'])}</p><div class="side-rule"><strong>观看方式</strong><p>点击“开始播放”后，画面先显示，随后朗读本段；本段结束再进入下一段。</p></div><details class="advanced"><summary>声音和语速</summary><label><input id="mute" type="checkbox"> 静音，按字幕时间播放</label><label for="rate">朗读语速<select id="rate"><option value="0.85">慢</option><option value="1" selected>正常</option><option value="1.15">快</option></select></label><p id="settings-note">设备的普通话声音和语速会在下一段生效。</p></details><div class="side-rule"><strong>可选操作</strong><p>先完整观看，再打开练习区。练习操作与自动演示状态分开保存。</p></div></aside></div><section class="practice-panel" id="practice-panel" hidden><h2>自己试一试</h2><p>这是浏览器里的手动实验状态，不会改写自动演示，也不提交成绩。</p><div class="practice-controls" id="practice-controls"></div><p class="practice-error" id="practice-error" role="status" aria-live="polite"></p><div class="practice-output" id="practice-output">选择一个操作，观察结果。</div><div class="practice-visual" id="practice-visual"></div></section></main><script>window.LESSON_DEFINITION={json_data};{RUNTIME}</script></body></html>'''


def manifest_for(lesson):
    scenes=[];prompts=[]
    for i,s in enumerate(lesson["steps"],1):
        scene_id=f"scene-{i:02d}"
        scenes.append({"id":scene_id,"title":s["title"],"summary":s["text"]})
        prompts.append({"id":scene_id+"-read","scene_id":scene_id,"text":s["text"],"trigger":"SCENE_ENTER"})
    return {"schema_version":"k12-interactive-v1","content_key":"autoplay-"+lesson["key"],"title":lesson["title"],"purpose":"LESSON","stage":lesson["stage"],"subject":lesson["subject"],"entry":"index.html","cover":"assets/cover.svg","summary":lesson["summary"],"knowledge_points":lesson["knowledge_points"],"capabilities":["SCENES"],"scenes":scenes,"prompts":prompts}


def build():
    lessons=build_lessons()
    # Erase only generated output subdirectories and known generated files in our new delivery folder.
    for name in ("standalone","packages"):
        path=ROOT/name
        if path.exists(): shutil.rmtree(path)
        path.mkdir(parents=True)
    (ROOT/"assets").mkdir(exist_ok=True)
    catalog=[]
    for lesson in lessons:
        stage_dir={"PRIMARY_LOWER":"primary-lower","PRIMARY_UPPER":"primary-upper","JUNIOR":"junior","SENIOR":"senior"}[lesson["stage"]]
        standalone=ROOT/"standalone"/stage_dir
        standalone.mkdir(parents=True,exist_ok=True)
        html=html_document(lesson)
        html_path=standalone/(lesson["file"]+".html")
        html_path.write_text(html,encoding="utf-8")
        pkg_key=lesson["key"].removeprefix("primary-lower-").removeprefix("primary-upper-").removeprefix("junior-").removeprefix("senior-")
        zip_name=lesson["key"]+".zip"
        manifest=manifest_for(lesson)
        cover=cover_svg(lesson)
        with zipfile.ZipFile(ROOT/"packages"/zip_name,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
            for name, data in [("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n"),("index.html",html),("assets/cover.svg",cover)]:
                entry=zipfile.ZipInfo(name,date_time=(2026,10,1,0,0,0))
                entry.compress_type=zipfile.ZIP_DEFLATED
                entry.external_attr=0o100644 << 16
                zf.writestr(entry,data)
        cover_path=ROOT/"assets"/(lesson["key"]+"-cover.svg")
        cover_path.write_text(cover,encoding="utf-8")
        verification={"files":"generated","browser":"not yet checked","platform":"not verified"}
        verification_path=SOURCE/"verification.json"
        if verification_path.exists():
            old=json.loads(verification_path.read_text(encoding="utf-8"))
            verification=old.get(lesson["key"],verification)
        catalog.append({"id":lesson["key"],"title":lesson["title"],"stage":lesson["stage"],"suggested_grades":lesson["grades"],"subject":lesson["subject"],"knowledge_points":lesson["knowledge_points"],"standalone_html":html_path.relative_to(ROOT).as_posix(),"package_zip":("packages/"+zip_name),"cover":"assets/"+cover_path.name,"summary":lesson["summary"],"verification":verification})
    (ROOT/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    preview=[]
    for stage, (label, grades) in STAGES.items():
        entries=[x for x in catalog if x["stage"]==stage]
        cards=''.join(f'''<article class="card"><a href="{esc(e['standalone_html'])}"><img src="{esc(e['cover'])}" alt="{esc(e['title'])}课件封面"><h3>{esc(e['title'])}</h3></a><p class="grade">{label} · {grades}</p><p>{esc(next(x['objective'] for x in lessons if x['key']==e['id']))}</p><p class="points">知识点：{esc('、'.join(e['knowledge_points']))}</p><a class="open" href="{esc(e['standalone_html'])}">打开课件</a></article>''' for e in entries)
        preview.append(f'<section class="group"><h2>{label} <span>{grades}</span></h2><div class="cards">{cards}</div></section>')
    preview_html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>霜铃 K12 自动播放教学样例</title><style>*{box-sizing:border-box}body{margin:0;background:#f2f4f3;color:#26364a;font:17px/1.55 system-ui,-apple-system,"Noto Sans CJK SC","Microsoft YaHei",sans-serif}.wrap{max-width:1320px;margin:auto;padding:28px 22px 50px}h1{font-size:clamp(25px,4vw,38px);margin:0 0 8px}.intro{color:#526579;max-width:850px;margin:0 0 28px}.group{margin:28px 0}.group h2{font-size:24px;border-bottom:1px solid #cfdad9;padding-bottom:10px}.group h2 span{font-size:16px;color:#647588;font-weight:500}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:#fff;border:1px solid #d5dfde;border-radius:16px;overflow:hidden;padding:0 0 14px}.card img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:cover}.card h3{font-size:19px;margin:12px 15px 3px}.card a{color:inherit;text-decoration:none}.card p{margin:5px 15px;color:#526579}.card .grade{color:#326c59;font-weight:650}.card .points{font-size:14px}.card .open{display:inline-block;margin:9px 15px 0;padding:8px 14px;border-radius:10px;background:#256e62;color:white;min-height:44px}.card a:focus-visible{outline:3px solid #237e72;outline-offset:3px}@media(max-width:800px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.wrap{padding:18px 12px}.cards{grid-template-columns:1fr}.group h2{font-size:21px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}</style></head><body><main class="wrap"><h1>霜铃 K12 · 自动播放教学样例</h1><p class="intro">四档学段共 12 个离线课件。打开任一课件后点一次“开始播放”，即可观看连续演示和字幕朗读；没有普通话声音时按字幕时间无声继续。每个课件下方都提供独立的可选实践。</p>'''+''.join(preview)+'''</main></body></html>'''
    (ROOT/"preview.html").write_text(preview_html,encoding="utf-8")
    print(f"Generated {len(lessons)} lessons, {sum(len(x['steps']) for x in lessons)} scenes")

if __name__=="__main__":
    build()
