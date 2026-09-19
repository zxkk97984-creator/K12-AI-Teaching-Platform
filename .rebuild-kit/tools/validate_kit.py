#!/usr/bin/env python3
"""Validate pack structure and DAG using only stdlib. Does not validate the app."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    errors=[]
    def require(ok,msg):
        if not ok:errors.append(msg)
    def read(name):return json.loads((ROOT/name).read_text(encoding="utf-8"))
    cat,progress=read("TASKS.json"),read("progress.json")
    tasks={t["id"]:t for t in cat["tasks"]}
    require(len(tasks)==len(cat["tasks"]),"任务ID重复")
    require(set(tasks)=={f"T{i:02}" for i in range(34)}|{f"O{i:02}" for i in range(1,5)},"任务集合缺失")
    require(cat["target_root"]==progress["target_root"]=="/home/zxk/Projects/K12","目标root错误")
    for task in tasks.values():
        tid=task["id"]
        require(tid in progress["tasks"],f"progress缺{tid}")
        for dep in task["depends_on"]:require(dep in tasks,f"{tid}缺前置{dep}")
        for gate in task["required_gates"]:require(gate in progress["gates"],f"{tid}缺门禁{gate}")
        for file in [task["card"],*task["read_files"]]:
            p=(ROOT/file).resolve()
            require(p.is_relative_to(ROOT) and p.is_file(),f"{tid}缺材料{file}")
    visiting=set();done=set()
    def visit(tid):
        if tid in visiting:raise ValueError(f"循环依赖:{tid}")
        if tid in done:return
        visiting.add(tid)
        for dep in tasks[tid]["depends_on"]:
            if dep in tasks:visit(dep)
        visiting.remove(tid);done.add(tid)
    try:
        for tid in tasks:visit(tid)
    except ValueError as exc:errors.append(str(exc))
    for path in ROOT.rglob("*.json"):
        try:json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:errors.append(f"JSON:{path.relative_to(ROOT)}:{exc}")
    for path in (ROOT/"tools").glob("*.py"):
        try:ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:errors.append(f"Python语法:{path.name}:{exc}")
    for skill in (ROOT/"platform/skills").iterdir():
        if not skill.is_dir():continue
        md=skill/"SKILL.md"
        require(md.is_file(),f"缺Skill:{skill.name}")
        if md.is_file():
            text=md.read_text(encoding="utf-8")
            require(text.startswith("---\nname: ") and "\ndescription: " in text,f"Skill frontmatter:{skill.name}")
        for ref in (skill/"references").glob("*.schema.json"):
            origin=ROOT/"contracts"/ref.name
            require(origin.is_file() and ref.read_bytes()==origin.read_bytes(),f"Skill契约漂移:{skill.name}/{ref.name}")
    forbidden={".env","dev.db","test.db","id_rsa","id_ed25519"}
    for p in ROOT.rglob("*"):
        require(p.name not in forbidden,f"不应包含敏感/环境文件:{p}")
        require(p.suffix.lower() not in {".ttf",".otf",".woff",".woff2"},f"禁止打包字体:{p}")
    if errors:
        print("FAIL\n"+"\n".join(errors));return 1
    print(f"PASS: {len(tasks)}任务，DAG无环，任务/规格引用存在，JSON/Python语法与Skill契约一致。")
    print("这不是未来K12应用测试，也没有调用Knodo、运行Docker或写入目标电脑。")
    return 0
if __name__=="__main__":sys.exit(main())
