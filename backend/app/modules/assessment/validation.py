"""Strict quiz-draft validation (T15 G2/G6/G7/G11).

Two layers, both mandatory:

1. the frozen ``contracts/quiz-draft.schema.json`` (via the T10 SchemaRegistry):
   closed objects (unknown fields rejected), id/length bounds, exactly three
   hints, one of the three supported question shapes;
2. the semantic rules the schema cannot express: unique question/option keys,
   the correct answer must be one of the options, an ordering answer must be a
   permutation of the items, question count/difficulty/type/objective/source
   must stay inside the trusted expectation, and every echoed id must match the
   request the backend actually made.

The student projection is derived here: it never contains ``correct_answer``,
``correct_order``, ``explanation`` or hint text, and ordering items are ordered
so the presentation order never equals the stored answer.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.modules.assessment.errors import QuizDraftRejected

SUPPORTED_TYPES = ("SINGLE_CHOICE", "TRUE_FALSE", "ORDERING")
STUDENT_NOTICE = "AI 生成草稿（未人工审校），仅用于私人随堂练习"

# A model may never mint review metadata for itself: these keys are rejected
# before the schema layer so the failure code is explicit (G11).
FAKE_REVIEW_FIELDS = frozenset(
    {
        "review_status",
        "reviewed",
        "reviewed_at",
        "reviewer",
        "reviewer_id",
        "review_note",
        "review_comment",
        "approved",
        "approval",
        "approver",
        "approver_id",
        "human_approved",
        "audit_status",
        "publication_status",
        "published",
    }
)

CODE_SCHEMA_INVALID = "SCHEMA_INVALID"
CODE_UNKNOWN_FIELD = "UNKNOWN_FIELD"
CODE_MULTIPLE_OBJECTS = "MULTIPLE_OBJECTS"
CODE_FAKE_REVIEW_FIELD = "FAKE_REVIEW_FIELD"
CODE_ECHO_MISMATCH = "ECHO_MISMATCH"
CODE_COUNT_MISMATCH = "COUNT_MISMATCH"
CODE_DIFFICULTY_NOT_ALLOWED = "DIFFICULTY_NOT_ALLOWED"
CODE_TYPE_NOT_ALLOWED = "TYPE_NOT_ALLOWED"
CODE_DUPLICATE_QUESTION_KEY = "DUPLICATE_QUESTION_KEY"
CODE_DUPLICATE_OPTION_KEY = "DUPLICATE_OPTION_KEY"
CODE_DUPLICATE_ITEM_KEY = "DUPLICATE_ITEM_KEY"
CODE_ANSWER_NOT_IN_OPTIONS = "ANSWER_NOT_IN_OPTIONS"
CODE_ORDERING_SET_MISMATCH = "ORDERING_SET_MISMATCH"
CODE_OBJECTIVE_NOT_ALLOWED = "OBJECTIVE_NOT_ALLOWED"
CODE_SOURCE_NOT_ALLOWED = "SOURCE_NOT_ALLOWED"
CODE_HINTS_NOT_DISTINCT = "HINTS_NOT_DISTINCT"


@dataclass(frozen=True)
class QuizExpectation:
    """Everything the trusted backend decided before calling the Designer."""

    request_id: str
    chapter_id: str
    curriculum_revision: str
    stage: str
    count: int
    difficulty: str
    question_types: tuple[str, ...]
    objective_ids: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]  # (source_id, revision) pairs

    def source_pairs(self) -> set[tuple[str, str]]:
        return set(self.sources)


@dataclass(frozen=True)
class ValidatedQuizDraft:
    payload: dict[str, Any]
    questions: tuple[dict[str, Any], ...]
    student_projection: dict[str, Any]

    @property
    def count(self) -> int:
        return len(self.questions)


def _reject(code: str, detail: str) -> QuizDraftRejected:
    return QuizDraftRejected(detail, code=code)


def _question_branches() -> dict[str, set[str]]:
    """Allowed question keys per declared type, from the frozen schema itself."""

    schema = default_registry().raw("quiz-draft")
    branches = schema["properties"]["questions"]["items"]["oneOf"]
    allowed: dict[str, set[str]] = {}
    for branch in branches:
        qtype = branch["properties"]["type"].get("const")
        if isinstance(qtype, str):
            allowed[qtype] = set(branch["properties"])
    return allowed


def _find_unknown_field(payload: dict[str, Any], *, schema_name: str = "quiz-draft") -> str | None:
    """Locate a field outside the frozen schema's closed objects.

    Pydantic's ``oneOf`` aggregates ``extra_forbidden`` from the branches that do
    not match the declared type, so the schema summary alone cannot tell a real
    unknown field from a legitimate ordering payload. This walker uses the same
    frozen schema to name the offending path precisely.
    """

    schema = default_registry().raw(schema_name)
    allowed_top = set(schema["properties"])
    for key in payload:
        if key not in allowed_top:
            return key
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return None
    branches = _question_branches()
    item_shapes = _question_item_shapes()
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        qtype = question.get("type")
        allowed = branches.get(qtype) if isinstance(qtype, str) else None
        if allowed is None:
            allowed = set().union(*branches.values()) if branches else set()
        for key in question:
            if key not in allowed:
                return f"questions[{index}].{key}"
        for field in ("options", "items"):
            entries = question.get(field)
            if not isinstance(entries, list):
                continue
            allowed_entry = item_shapes.get((qtype, field))
            if not allowed_entry:
                continue
            for position, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                for key in entry:
                    if key not in allowed_entry:
                        return f"questions[{index}].{field}[{position}].{key}"
        refs = question.get("source_refs")
        if isinstance(refs, list):
            for position, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    continue
                for key in ref:
                    if key not in ("source_id", "revision", "locator"):
                        return f"questions[{index}].source_refs[{position}].{key}"
    return None


def _question_item_shapes() -> dict[tuple[str, str], set[str]]:
    schema = default_registry().raw("quiz-draft")
    branches = schema["properties"]["questions"]["items"]["oneOf"]
    shapes: dict[tuple[str, str], set[str]] = {}
    for branch in branches:
        qtype = branch["properties"]["type"].get("const")
        for field in ("options", "items"):
            node = branch["properties"].get(field)
            if isinstance(node, dict) and isinstance(node.get("items"), dict):
                shapes[(qtype, field)] = set(node["items"]["properties"])
    return shapes


def _find_fake_review_fields(value: Any, *, path: str = "<root>") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key in FAKE_REVIEW_FIELDS:
                return f"{path}.{key}"
            found = _find_fake_review_fields(item, path=f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_fake_review_fields(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise _reject(code, detail)


def validate_quiz_draft(raw: object, *, expectation: QuizExpectation) -> ValidatedQuizDraft:
    """Validate one Designer payload or raise :class:`QuizDraftRejected`."""

    _require(isinstance(raw, dict), CODE_MULTIPLE_OBJECTS, "期望单个 JSON 对象")
    payload = copy.deepcopy(raw)

    fake_field = _find_fake_review_fields(payload)
    if fake_field is not None:
        # Never echo the submitted value: only the field path is reported.
        raise _reject(CODE_FAKE_REVIEW_FIELD, f"模型不得自带审核字段：{fake_field}")

    unknown = _find_unknown_field(payload)
    if unknown is not None:
        raise _reject(CODE_UNKNOWN_FIELD, f"题稿包含冻结 schema 之外的字段：{unknown}")

    schema_errors = default_registry().validate_response(Operation.QUIZ_DRAFT, payload)
    if schema_errors:
        raise _reject(
            CODE_SCHEMA_INVALID,
            "不符合冻结 quiz-draft schema：" + "; ".join(schema_errors[:3]),
        )

    for field, expected in (
        ("request_id", expectation.request_id),
        ("chapter_id", expectation.chapter_id),
        ("curriculum_revision", expectation.curriculum_revision),
        ("stage", expectation.stage),
    ):
        _require(
            payload.get(field) == expected,
            CODE_ECHO_MISMATCH,
            f"{field} 与受信请求不一致（不接受模型自造的课程/版本标识）",
        )

    questions = payload.get("questions")
    _require(isinstance(questions, list) and questions, CODE_SCHEMA_INVALID, "questions 为空")
    _require(
        len(questions) == expectation.count,
        CODE_COUNT_MISMATCH,
        f"题量 {len(questions)} 与策略允许的 {expectation.count} 不一致",
    )
    _require(
        payload.get("difficulty") == expectation.difficulty,
        CODE_DIFFICULTY_NOT_ALLOWED,
        "难度不在受信策略允许范围内",
    )

    seen_keys: set[str] = set()
    allowed_sources = expectation.source_pairs()
    for index, question in enumerate(questions):
        _require(isinstance(question, dict), CODE_SCHEMA_INVALID, f"questions[{index}] 不是对象")
        qtype = question.get("type")
        _require(
            qtype in expectation.question_types,
            CODE_TYPE_NOT_ALLOWED,
            f"题型 {qtype!r} 不在策略允许范围内",
        )
        question_key = question.get("question_key")
        _require(
            isinstance(question_key, str) and question_key not in seen_keys,
            CODE_DUPLICATE_QUESTION_KEY,
            f"question_key 重复：{question_key!r}",
        )
        seen_keys.add(question_key)
        _require(
            question.get("objective_id") in expectation.objective_ids,
            CODE_OBJECTIVE_NOT_ALLOWED,
            f"objective_id 不在本章目标白名单：{question.get('objective_id')!r}",
        )

        refs = question.get("source_refs") or []
        for ref in refs:
            pair = (ref.get("source_id"), ref.get("revision"))
            _require(
                pair in allowed_sources,
                CODE_SOURCE_NOT_ALLOWED,
                f"来源不在本章白名单：{pair[0]!r}@{pair[1]!r}",
            )

        hints = question.get("hints") or []
        _require(
            len(set(hints)) == len(hints),
            CODE_HINTS_NOT_DISTINCT,
            "三级提示必须逐级不同",
        )

        if qtype == "SINGLE_CHOICE":
            _validate_single_choice(question)
        elif qtype == "TRUE_FALSE":
            # JSON strings like "true" must not be coerced into a boolean answer.
            _require(
                isinstance(question.get("correct_answer"), bool),
                CODE_ANSWER_NOT_IN_OPTIONS,
                "判断题答案必须是 JSON 布尔值",
            )
        elif qtype == "ORDERING":
            _validate_ordering(question)

    projection = build_student_projection(payload)
    return ValidatedQuizDraft(
        payload=payload,
        questions=tuple(copy.deepcopy(questions)),
        student_projection=projection,
    )


def _validate_single_choice(question: dict[str, Any]) -> None:
    options = question.get("options") or []
    keys = [option.get("key") for option in options]
    _require(
        len(set(keys)) == len(keys),
        CODE_DUPLICATE_OPTION_KEY,
        f"选项 key 重复：{keys}",
    )
    _require(
        question.get("correct_answer") in keys,
        CODE_ANSWER_NOT_IN_OPTIONS,
        "正确答案不在选项集合内",
    )


def _validate_ordering(question: dict[str, Any]) -> None:
    items = question.get("items") or []
    item_keys = [item.get("key") for item in items]
    _require(
        len(set(item_keys)) == len(item_keys),
        CODE_DUPLICATE_ITEM_KEY,
        "排序项 key 重复",
    )
    order = question.get("correct_order") or []
    _require(
        len(order) == len(item_keys) and set(order) == set(item_keys),
        CODE_ORDERING_SET_MISMATCH,
        "排序答案必须是全部排序项的一个排列（不缺、不重、不多）",
    )


def _presentation_order(question_key: str, item_keys: list[str]) -> list[str]:
    """Deterministic order that never equals the stored correct order."""

    ranked = sorted(
        item_keys, key=lambda key: hashlib.sha256(f"{question_key}|{key}".encode()).hexdigest()
    )
    return ranked


def build_student_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Student-facing projection: no answers, no explanation, no hint text."""

    questions: list[dict[str, Any]] = []
    for question in payload.get("questions", []):
        qtype = question["type"]
        projected: dict[str, Any] = {
            "question_key": question["question_key"],
            "objective_id": question["objective_id"],
            "type": qtype,
            "stem": question["stem"],
            "source_refs": copy.deepcopy(question["source_refs"]),
            "hint_count": len(question.get("hints") or []),
        }
        if qtype == "SINGLE_CHOICE":
            projected["options"] = [
                {"key": option["key"], "text": option["text"]} for option in question["options"]
            ]
        elif qtype == "ORDERING":
            item_keys = [item["key"] for item in question["items"]]
            order = _presentation_order(question["question_key"], item_keys)
            if order == list(question.get("correct_order") or []):
                order = order[1:] + order[:1]
            by_key = {item["key"]: item["text"] for item in question["items"]}
            projected["items"] = [{"key": key, "text": by_key[key]} for key in order]
        else:  # TRUE_FALSE renders two fixed local choices; no payload needed
            projected["options"] = [
                {"key": "TRUE", "text": "对"},
                {"key": "FALSE", "text": "错"},
            ]
        questions.append(projected)

    return {
        "schema_version": "k12.quiz.student.v1",
        "request_id": payload.get("request_id"),
        "chapter_id": payload.get("chapter_id"),
        "curriculum_revision": payload.get("curriculum_revision"),
        "stage": payload.get("stage"),
        "difficulty": payload.get("difficulty"),
        "questions": questions,
        "notice": STUDENT_NOTICE,
    }
