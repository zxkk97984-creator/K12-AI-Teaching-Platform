"""T16 H4/H6/H7: deterministic scoring for the three frozen question types."""

from __future__ import annotations

import pytest

from app.modules.assessment.scoring import (
    SCORING_VERSION,
    AnswerRejected,
    ScoringUnavailable,
    score_answer,
)

SINGLE = {
    "type": "SINGLE_CHOICE",
    "options": [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
    "correct_answer": "A",
}
TRUE_FALSE = {"type": "TRUE_FALSE", "correct_answer": True}
ORDERING = {
    "type": "ORDERING",
    "items": [{"key": "A", "text": "一"}, {"key": "B", "text": "二"}, {"key": "C", "text": "三"}],
    "correct_order": ["A", "B", "C"],
}


def test_single_choice_is_exact_key_match():
    assert score_answer(SINGLE, "A").is_correct is True
    assert score_answer(SINGLE, "B").is_correct is False
    assert score_answer(SINGLE, "A").scoring_version == SCORING_VERSION


def test_single_choice_rejects_unknown_key_without_scoring():
    with pytest.raises(AnswerRejected):
        score_answer(SINGLE, "Z")
    with pytest.raises(AnswerRejected):
        score_answer(SINGLE, 1)


def test_true_false_requires_json_boolean():
    assert score_answer(TRUE_FALSE, True).is_correct is True
    assert score_answer(TRUE_FALSE, False).is_correct is False
    for bad in ("true", "True", 1, 0, None, ["true"]):
        with pytest.raises(AnswerRejected):
            score_answer(TRUE_FALSE, bad)


def test_ordering_compares_complete_sequence_not_set():
    assert score_answer(ORDERING, ["A", "B", "C"]).is_correct is True
    # right items, wrong order → wrong (not a set comparison)
    assert score_answer(ORDERING, ["B", "A", "C"]).is_correct is False
    assert score_answer(ORDERING, ["C", "B", "A"]).is_correct is False


def test_ordering_rejects_incomplete_duplicate_or_extra_items():
    for bad in (["A", "B"], ["A", "B", "C", "D"], ["A", "A", "C"], "A,B,C", [1, 2, 3]):
        with pytest.raises(AnswerRejected):
            score_answer(ORDERING, bad)


def test_unsupported_or_corrupt_snapshot_is_a_system_failure():
    with pytest.raises(ScoringUnavailable):
        score_answer({"type": "ESSAY", "correct_answer": "x"}, "x")
    with pytest.raises(ScoringUnavailable):
        score_answer({"type": "SINGLE_CHOICE", "options": [], "correct_answer": "A"}, "A")
    with pytest.raises(ScoringUnavailable):
        score_answer({"type": "ORDERING", "items": [], "correct_order": []}, ["A"])
    corrupt = {
        "type": "SINGLE_CHOICE",
        "options": [{"key": "A", "text": "对"}],
        "correct_answer": "Z",  # snapshot disagrees with itself
    }
    with pytest.raises(ScoringUnavailable):
        score_answer(corrupt, "A")
