#!/usr/bin/env python3
"""Print a task prompt. Never executes project commands or writes progress."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "DONE", "FAILED"}

def load_json(name: str) -> dict:
    path = ROOT / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"无法读取 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path}必须为JSON对象")
    return value

def blockers(task: dict, progress: dict) -> list[str]:
    result = []
    for dep in task["depends_on"]:
        state = progress["tasks"].get(dep, {})
        if state.get("status") != "DONE" or not state.get("evidence"):
            result.append(f"前置{dep}未完成或缺证据")
    for gate in task["required_gates"]:
        state = progress["gates"].get(gate, {})
        if state.get("status") != "PASS" or not state.get("evidence"):
            result.append(f"{gate}未通过或缺依据")
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["next", "show", "status"])
    parser.add_argument("task", nargs="?")
    parser.add_argument("--include-optional", action="store_true")
    args = parser.parse_args()
    catalog, progress = load_json("TASKS.json"), load_json("progress.json")
    tasks = catalog["tasks"]
    if catalog["target_root"] != progress["target_root"]:
        raise SystemExit("任务清单与progress目标路径不一致")
    for task in tasks:
        state = progress["tasks"].get(task["id"], {}).get("status")
        if state not in STATUSES:
            raise SystemExit(f"{task['id']}状态非法: {state}")
    if args.action == "status":
        for task in tasks:
            if task["optional"] and not args.include_optional:
                continue
            state = progress["tasks"][task["id"]]["status"]
            why = "; ".join(blockers(task, progress))
            print(f"{task['id']} [{state}] {task['title']}" + (f" | {why}" if why else ""))
        return 0
    if args.action == "show":
        selected = next((task for task in tasks if task["id"] == args.task), None)
        if selected is None:
            raise SystemExit("show必须指定存在的任务，例如 show T04")
    else:
        eligible = [task for task in tasks
                    if (not task["optional"] or args.include_optional)
                    and progress["tasks"][task["id"]]["status"] != "DONE"
                    and not blockers(task, progress)]
        # Resume unfinished work before starting another independent task.
        selected = next((task for task in eligible if progress["tasks"][task["id"]]["status"] in {"IN_PROGRESS", "FAILED"}), None)
        if selected is None and eligible:
            selected = eligible[0]
        if selected is None:
            print("没有依赖与门禁已满足的未完成任务。请检查progress和真实外部依据；本工具不会自动改PASS/DONE。")
            for task in tasks:
                if not task["optional"] and progress["tasks"][task["id"]]["status"] != "DONE":
                    print(task["id"] + ": " + "; ".join(blockers(task, progress)))
            return 2
    path = (ROOT / selected["card"]).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise SystemExit("任务卡路径无效")
    print(f"目标项目：{catalog['target_root']}\n执行包：{ROOT}\n")
    why = blockers(selected, progress)
    if why:
        print("【尚不能执行真实依赖步骤】" + "; ".join(why) + "\n")
    print(path.read_text(encoding="utf-8"))
    print("\n先核对现场和相关代码。完成后写真实证据并更新progress；本输出不是已执行结果。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
