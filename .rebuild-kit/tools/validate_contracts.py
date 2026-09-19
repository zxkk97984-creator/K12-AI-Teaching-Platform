#!/usr/bin/env python3
"""Offline reference validators for the proposed local application contracts.
Not a Knodo client, production sanitizer, authorization layer, or correctness proof.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

def schema_validate(name: str, payload: dict[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise RuntimeError("需要jsonschema；使用本包requirements-validation.txt在专用验证环境安装") from exc
    schema = json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)

def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def check_sources(refs: list[dict], request: dict) -> None:
    available = {(s["source_id"], s["revision"], s["locator"]) for s in request["knowledge_context"]}
    for ref in refs:
        need((ref["source_id"], ref["revision"], ref["locator"]) in available, "来源ID/版本/定位不在本轮授权集合")

def validate_teaching(request: dict, response: dict) -> None:
    schema_validate("teaching-request", request)
    schema_validate("teaching-response", response)
    for key in ("request_id", "lesson_session_id", "base_revision", "curriculum_revision"):
        need(response[key] == request[key], f"{key}不匹配")
    grade = request["learner"]["grade"]
    if grade is not None:
        stage = "PRIMARY_LOWER" if grade <= 3 else "PRIMARY_UPPER" if grade <= 6 else "JUNIOR" if grade <= 9 else "SENIOR"
        need(stage == request["learner"]["stage"], "grade与stage不匹配")
    need(request["operation"] != "CODE_FEEDBACK" or request["code_feedback_facts"] is not None, "代码辅导缺少真实run事实")
    need(len(response["message_markdown"]) <= request["limits"]["max_reply_chars"], "回复超过本轮长度预算")
    check_sources(response["source_refs"], request)
    valid_evidence = {e["id"] for e in request["evidence"]}
    need(set(response["evidence_refs"]) <= valid_evidence, "引用了未授权学习证据")
    phase = response["phase_suggestion"]
    need(phase is None or phase in request["allowed_phase_suggestions"], "phase建议不在允许集合")
    action = response["action"]
    if action is None:
        return
    kind = action["type"]
    need(kind in request["allowed_actions"], "动作未获允许")
    if kind == "OFFER_QUIZ":
        need(set(action["objective_ids"]) <= set(request["chapter"]["objective_ids"]), "测验目标不属于本章")
        need(action["question_count"] <= request["limits"]["max_quiz_questions"], "题量超过本轮预算")
        need(action["difficulty"] in request["limits"]["allowed_difficulties"], "题目难度不在允许集合")
    elif kind == "OPEN_RESOURCE":
        need(action["resource_id"] in request["allowed_resource_ids"], "资源未授权")
    elif kind == "OPEN_ANIMATION":
        need(action["resource_id"] in request["allowed_animation_ids"], "动画未授权")
    elif kind == "OPEN_CODE_TASK":
        need(action["task_id"] in request["allowed_code_task_ids"], "编程任务未授权")

def validate_designer(request: dict, response: dict) -> None:
    schema_validate("designer-request", request)
    kind = request["operation"]
    schema_validate("quiz-draft" if kind == "QUIZ_DRAFT" else "lesson-package-draft", response)
    for key in ("request_id", "chapter_id", "curriculum_revision", "stage"):
        need(response[key] == request[key], f"{key}不匹配")
    if kind == "QUIZ_DRAFT":
        spec = request["quiz_spec"]
        need(len(response["questions"]) == spec["count"], "题量不符")
        need(response["difficulty"] == spec["difficulty"], "难度不符")
        qkeys = [q["question_key"] for q in response["questions"]]
        need(len(qkeys) == len(set(qkeys)), "题目key重复")
        for q in response["questions"]:
            need(q["type"] in spec["question_types"], "题型未授权")
            need(q["objective_id"] in request["objective_ids"], "目标不属于本章")
            check_sources(q["source_refs"], request)
            if q["type"] == "SINGLE_CHOICE":
                keys = [o["key"] for o in q["options"]]
                need(len(keys) == len(set(keys)), "选项key重复")
                need(q["correct_answer"] in keys, "答案不属于选项")
            elif q["type"] == "ORDERING":
                keys = [o["key"] for o in q["items"]]
                need(len(keys) == len(set(keys)), "排序项key重复")
                need(set(q["correct_order"]) == set(keys), "排序答案未精确覆盖项目")
    else:
        check_sources(response["source_refs"], request)
        for act in response["activities"]:
            need(act["suggested_resource_id"] is None or act["suggested_resource_id"] in request["allowed_resource_ids"], "活动引用未授权资源")
        spec = request["lesson_spec"]
        for animation in response["animation_specs"]:
            need(animation["template"] in spec["allowed_animation_templates"], "动画模板未授权")
            check_sources(animation["source_refs"], request)
            if animation["template"] == "BINARY_SEARCH":
                need(animation["values"] == sorted(animation["values"]), "二分查找输入必须有序")
                need(animation["target"] is not None, "二分查找缺target")
        need(spec["asset_requests_allowed"] or not response["asset_requests"], "未允许素材需求")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["teaching", "designer"])
    parser.add_argument("request", type=Path)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    response = json.loads(args.response.read_text(encoding="utf-8"))
    (validate_teaching if args.mode == "teaching" else validate_designer)(request, response)
    print("PASS: 本地结构与部分交叉语义校验；不证明事实正确、实际鉴权或Knodo接口兼容。")

if __name__ == "__main__":
    main()
