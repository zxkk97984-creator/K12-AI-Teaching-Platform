#!/usr/bin/env python3
"""Static/package and lesson-computation verification for the generated batch."""
from __future__ import annotations
import importlib.util
import json
import re
import sys
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
BACKEND=PROJECT/"backend"
sys.path.insert(0,str(BACKEND))
from app.modules.interactive.package import read_package, build_document

spec=importlib.util.spec_from_file_location("lesson_builder",ROOT/"source"/"build.py")
buildmod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=buildmod
spec.loader.exec_module(buildmod)
lessons=buildmod.build_lessons()
errors=[]
checks=[]

def check(condition,message):
    if not condition: errors.append(message)
    checks.append({"name":message,"passed":bool(condition)})

check(len(lessons)==12,"生成定义恰好 12 个样例")
counts=Counter(x["stage"] for x in lessons)
check(counts=={"PRIMARY_LOWER":3,"PRIMARY_UPPER":3,"JUNIOR":3,"SENIOR":3},"四档学段各 3 个样例")

# Bundle and manifest validation uses the project's actual import parser and HTML document builder.
keys=set()
for lesson in lessons:
    key=lesson["key"]
    manifest_path=ROOT/"packages"/(key+".zip")
    stage_dir={"PRIMARY_LOWER":"primary-lower","PRIMARY_UPPER":"primary-upper","JUNIOR":"junior","SENIOR":"senior"}[lesson["stage"]]
    html_path=ROOT/"standalone"/stage_dir/(lesson["file"]+".html")
    cover_path=ROOT/"assets"/(key+"-cover.svg")
    check(html_path.is_file(),f"{key}: 单文件 HTML 存在")
    check(manifest_path.is_file(),f"{key}: ZIP 存在")
    check(cover_path.is_file() and "<svg" in cover_path.read_text(encoding="utf-8"),f"{key}: 预览封面是有效绘制的 SVG")
    keys.add(key)
    if not (html_path.is_file() and manifest_path.is_file()):
        continue
    standalone=html_path.read_bytes()
    with zipfile.ZipFile(manifest_path) as zf:
        names=zf.namelist()
        check(set(names)=={"manifest.json","index.html","assets/cover.svg"},f"{key}: ZIP 根目录含清单、入口和封面")
        check(zf.getinfo("manifest.json").file_size+zf.getinfo("index.html").file_size+zf.getinfo("assets/cover.svg").file_size<100*1024*1024,f"{key}: 解压体积低于 100 MB")
        check(manifest_path.stat().st_size<20*1024*1024,f"{key}: ZIP 低于 20 MB")
        check(zf.read("index.html")==standalone,f"{key}: 单文件与 ZIP 入口完全相同")
        check(zf.read("assets/cover.svg")==cover_path.read_bytes(),f"{key}: ZIP 封面与目录封面相同")
        for name in names:
            check(not name.startswith("/") and ".." not in Path(name).parts,f"{key}: 包路径安全 {name}")
        default={"stage":lesson["stage"],"purpose":"LESSON","title":lesson["title"],"subject":lesson["subject"],"slug":key}
        try:
            files,parsed=read_package(manifest_path.read_bytes(),manifest_path.name,default=default)
            check(parsed.purpose=="LESSON" and parsed.stage==lesson["stage"],f"{key}: 项目包解析器接受 manifest")
            check(len(parsed.scenes)==len(lesson["steps"]) and len(parsed.prompts)==len(lesson["steps"]),f"{key}: 包解析场景与讲解数量一致")
            built=build_document(files,parsed,"/* project bridge */")
            check("Content-Security-Policy" in built and "window.__K12_ASSETS__" in built,f"{key}: 项目 HTML 构建器生成隔离文档")
        except Exception as exc:
            errors.append(f"{key}: 项目包解析失败：{type(exc).__name__}: {exc}")
            checks.append({"name":f"{key}: 项目包解析器接受并构建","passed":False})
        manifest=json.loads(zf.read("manifest.json"))
        check(manifest["purpose"]=="LESSON" and manifest["stage"]==lesson["stage"],f"{key}: manifest 用途与学段正确")
        check(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*",manifest["content_key"]) is not None,f"{key}: content_key 格式合法")
        check(manifest["content_key"] not in keys-{key},f"{key}: content_key 不重复")
        check(len(manifest["scenes"])==len(manifest["prompts"])<=100,f"{key}: 场景/讲解数量不超过 100 且成对")
        check(len(manifest["knowledge_points"])<=12 and all(len(x)<=1000 for x in [manifest["summary"]]),f"{key}: 清单字段长度在范围内")
        scene_ids=[x["id"] for x in manifest["scenes"]]
        prompt_ids=[x["id"] for x in manifest["prompts"]]
        check(len(set(scene_ids))==len(scene_ids) and len(set(prompt_ids))==len(prompt_ids),f"{key}: 场景和讲解 ID 唯一")
        check(all(p["scene_id"]==s["id"] and p["id"]==s["id"]+"-read" and p["trigger"]=="SCENE_ENTER" for p,s in zip(manifest["prompts"],manifest["scenes"])),f"{key}: scene/prompt 一一对应且采用 -read 命名")
        check(all(2<=len(p["text"])<=500 for p in manifest["prompts"]),f"{key}: 每段讲解长度符合约束")
    html=standalone.decode("utf-8")
    check("SpeechSynthesisUtterance" in html and "utterance.onend" in html,f"{key}: 包含真实 TTS ended 事件推进逻辑")
    check("window.K12.ready()" in html and "workspace.register" in html,f"{key}: 平台桥接从 ready/register 开始")
    check("scene-" in html and "-read" in html,f"{key}: 场景和讲解标识内联")
    check("<iframe" not in html.lower() and "<form" not in html.lower() and "@import" not in html.lower(),f"{key}: 无 iframe、form 或 CSS @import")
    check("setInterval(" not in html and "eval(" not in html and "new Function" not in html,f"{key}: 无强制翻场计时器或学生代码执行")
    for external in re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']",html,re.I):
        check(not re.match(r"(?:https?:)?//",external) and not external.lower().endswith((".js",".css",".png",".jpg",".svg",".woff",".woff2")),f"{key}: 无外部资源引用 {external}")

# Actual preview index paths.
preview=(ROOT/"preview.html").read_text(encoding="utf-8")
class Hrefs(HTMLParser):
    def __init__(self):super().__init__();self.hrefs=[];self.srcs=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="a" and a.get("href"):self.hrefs.append(a["href"])
        if tag=="img" and a.get("src"):self.srcs.append(a["src"])
links=Hrefs();links.feed(preview)
check(len(links.hrefs)==24,"目录含 12 个课件卡片链接及 12 个打开链接")
check(all((ROOT/p).is_file() for p in links.hrefs),"目录中每个课件链接均可用")
check(all((ROOT/p).is_file() for p in links.srcs),"目录中每张封面图片均存在")
check("<iframe" not in preview.lower(),"目录页不嵌入 iframe")

# Teaching computation invariants.
by={x["kind"]:x for x in lessons}
bubble=by["cards-bubble-sort"]
check(bubble["data"]["sorted"]==[1,2,3,4,5],"冒泡排序最终为 [1,2,3,4,5]")
for st in bubble["steps"]:
    state=st["state"]
    if state.get("cards") and state.get("previousCards"):
        before=state["previousCards"];after=state["cards"]
        check(Counter(x["value"] for x in before)==Counter(x["value"] for x in after),"冒泡排序比较前后元素数值无增删")
        check(all(state.get("left")==x and state.get("right")==x+1 for x in [state.get("left")]) if state.get("left") is not None else True,"冒泡排序只比较相邻项")
metrics_l=by["classification-metrics"]
check(metrics_l["data"]["expected"]["0.5"]=={"tp":3,"fp":2,"fn":1,"tn":2},"0.50 阈值混淆计数符合指定结果")
check(metrics_l["data"]["expected"]["0.65"]=={"tp":2,"fp":1,"fn":2,"tn":3},"0.65 阈值混淆计数符合指定结果")
for threshold,expected in [(0.5,{"tp":3,"fp":2,"fn":1,"tn":2}),(0.65,{"tp":2,"fp":1,"fn":2,"tn":3})]:
    calc=buildmod.metrics(metrics_l["data"]["records"],threshold)
    check(calc["counts"]==expected,f"阈值 {threshold:.2f} 的指标由数据实际计算")
    if threshold==.5:
        check(calc["accuracy"]==.625 and calc["precision"]==.6 and calc["recall"]==.75,"0.50 准确率、精确率和召回率正确")
    else:
        check(calc["accuracy"]==.625 and round(calc["precision"],3)==.667 and calc["recall"]==.5,"0.65 准确率、精确率和召回率正确")
short=by["shortest-path"]
result=buildmod.dijkstra(short["data"]["nodes"],short["data"]["edges"],"A")
path=buildmod.path_to(result["prev"],"A","E")
check(path==["A","C","B","D","E"] and result["dist"]["E"]==10,"Dijkstra 从边权计算得到 A-C-B-D-E，总成本 10")
check(result["dist"]["F"]==float("inf"),"Dijkstra 的 F 节点不可达")
grad=by["gradient-descent"]
alpha=grad["data"]["alpha"];x=grad["data"]["x0"]
for _ in range(6):x=x-alpha*2*x
check(abs(x-0.470596)<1e-6,"梯度下降六次更新按指定公式计算")
x=4
for _ in range(3):x=x-1.1*2*x
check(abs(x+6.912)<1e-9 and x*x>16,"过大步长对照实际越过最低点并远离")
linear=by["linear-search"]
check(linear["steps"][4]["state"]["current"]==3 and "第 4 项" in linear["steps"][4]["text"] and "下标为 3" in linear["steps"][4]["text"],"线性查找目标 9 在第 4 项、下标 3 停止")
check(linear["steps"][-1]["state"]["current"] is None and len(linear["steps"][-1]["state"]["checked"])==6,"线性查找未命中后检查 6 项并停止")
robot=by["robot-instructions"]
check(any(x["state"]["status"]=="blocked" for x in robot["steps"]),"机器人错误路线遇障并停止")
check(robot["steps"][-1]["state"]["status"]=="done" and robot["steps"][-1]["state"]["position"]==[0,4],"机器人改正路线到达终点")
pixels=by["pixels-build-picture"]["data"]
check(all(pixels["matrix"][r*2+i][c*2+j]==pixels["coarse"][r][c] for r in range(4) for c in range(4) for i in range(2) for j in range(2)),"粗细像素网格由同一颜色矩阵生成")
train=by["training-and-testing"]
check(train["data"]["correct"]==2,"最近邻测试正确数量从三次预测实际计算为 2")
check(all("truth" not in st["state"].get("test",{}) for st in train["steps"] if st["state"].get("test") and st["state"].get("truth") is None),"测试点真实标签仅在预测后揭示")

REPORTS=ROOT.parent/"frontend"/"test-results"/"autoplay-examples-static"
REPORTS.mkdir(parents=True,exist_ok=True)
result={"status":"passed" if not errors else "failed","sample_count":len(lessons),"stage_counts":dict(counts),"scene_count":sum(len(x["steps"]) for x in lessons),"checks_passed":sum(x["passed"] for x in checks),"checks_total":len(checks),"errors":errors,"checks":checks,"project_package_parser":"read_package + build_document","platform_actual_import":"not verified"}
(REPORTS/"static-validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
lines=["# 静态与内容包检查", "", f"状态：{'通过' if not errors else '失败'}。共 {result['checks_passed']}/{result['checks_total']} 项检查通过，12 个样例、{result['scene_count']} 个场景。", "", "检查包括清单字段与引用、项目包解析器、隔离 HTML 构建、文件边界、目录链接和关键算法结果。没有访问数据库。", "", "平台实际导入：未验证。", ""]
if errors:lines+= ["## 失败项", ""]+["- "+e for e in errors]
(REPORTS/"static-validation.md").write_text("\n".join(lines),encoding="utf-8")
print(f"static validation: {result['status']} ({result['checks_passed']}/{result['checks_total']})")
for err in errors:print("ERROR:",err)
if errors:raise SystemExit(1)
