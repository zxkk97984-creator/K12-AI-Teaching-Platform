"""Deterministic quiz scoring (T16 H4/H6/H7).

Scoring is pure local logic over the immutable snapshot: no model, no gateway
and no client-supplied trust values. Three shapes are supported — exactly the
frozen quiz-draft types. ``ORDERING`` compares the *complete sequence*; a
correct set in the wrong order is wrong.

Two distinct failure kinds:

* :class:`AnswerRejected` — the student submitted something structurally
  invalid (unknown option key, duplicate ordering item, wrong JSON type). This
  is a 4xx client error and never counts as an attempt or as a wrong answer.
* :class:`ScoringUnavailable` — the scoring pipeline itself cannot run
  (unsupported snapshot type, corrupt answer payload). This is a *system*
  failure: it must not be recorded as a student mistake or a zero score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCORING_VERSION = "k12.quiz.scoring.v1"
REVIEW_THRESHOLDS_VERSION = "k12.quiz.review-thresholds.v1"
SUPPORTED_TYPES = ("SINGLE_CHOICE", "TRUE_FALSE", "ORDERING")


class AnswerRejected(Exception):
    """Structurally invalid submission from the client (client error)."""

    code = "INVALID_ANSWER"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ScoringUnavailable(Exception):
    """The scoring pipeline cannot produce a verdict (system failure)."""

    code = "SCORING_UNAVAILABLE"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class ScoringResult:
    is_correct: bool
    normalised_answer: Any
    scoring_version: str = SCORING_VERSION


def _option_keys(question: dict[str, Any]) -> set[str]:
    options = question.get("options")
    if not isinstance(options, list) or not options:
        raise ScoringUnavailable("选项缺失，无法判分")
    keys = {option.get("key") for option in options if isinstance(option, dict)}
    if None in keys or len(keys) != len(options):
        raise ScoringUnavailable("选项 key 缺失或重复")
    return keys  # type: ignore[return-value]


def _item_keys(question: dict[str, Any]) -> list[str]:
    items = question.get("items")
    if not isinstance(items, list) or not items:
        raise ScoringUnavailable("排序项缺失，无法判分")
    keys = [item.get("key") for item in items if isinstance(item, dict)]
    if len(keys) != len(items) or any(not isinstance(key, str) for key in keys):
        raise ScoringUnavailable("排序项 key 缺失")
    return keys  # type: ignore[return-value]


def score_answer(question: dict[str, Any], answer: Any) -> ScoringResult:
    qtype = question.get("type")
    if qtype not in SUPPORTED_TYPES:
        raise ScoringUnavailable(f"不支持的题型：{qtype!r}")

    if qtype == "SINGLE_CHOICE":
        keys = _option_keys(question)
        if not isinstance(answer, str) or answer not in keys:
            raise AnswerRejected("答案必须是选项 key 之一")
        expected = question.get("correct_answer")
        if not isinstance(expected, str) or expected not in keys:
            raise ScoringUnavailable("快照中的正确答案无效")
        return ScoringResult(is_correct=answer == expected, normalised_answer=answer)

    if qtype == "TRUE_FALSE":
        if not isinstance(answer, bool):
            raise AnswerRejected("判断题答案必须是 JSON 布尔值")
        expected = question.get("correct_answer")
        if not isinstance(expected, bool):
            raise ScoringUnavailable("快照中的判断题答案无效")
        return ScoringResult(is_correct=answer == expected, normalised_answer=answer)

    item_keys = _item_keys(question)
    if not isinstance(answer, list) or any(not isinstance(key, str) for key in answer):
        raise AnswerRejected("排序答案必须是 key 数组")
    if (
        len(answer) != len(item_keys)
        or set(answer) != set(item_keys)
        or len(set(answer)) != len(answer)
    ):
        raise AnswerRejected("排序答案必须是全部排序项的一个排列")
    expected_order = question.get("correct_order")
    if not isinstance(expected_order, list) or set(expected_order) != set(item_keys):
        raise ScoringUnavailable("快照中的排序答案无效")
    # Complete-sequence comparison: the right items in the wrong order are wrong.
    return ScoringResult(is_correct=answer == expected_order, normalised_answer=list(answer))
