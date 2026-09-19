"""T14 F4/F5/F11: age-band policy, illegal grades, evidence caps, no ranking."""

from __future__ import annotations

import pytest

from app.modules.learning.policy import (
    DIFFICULTY_ORDER,
    LearningPolicyError,
    build_policy,
    evidence_level_from,
    expected_stage_for_grade,
)

SNAPSHOT_KEYS = {
    "schema_version",
    "stage",
    "grade",
    "preferred_style",
    "evidence_level",
    "allowed_actions",
    "max_quiz_questions",
    "allowed_difficulties",
    "allowed_question_types",
    "max_explanation_chars",
    "media_candidates",
    "scaffolding",
    "proactive_opening_allowed",
}


def _policy(stage: str, grade: int | None, *, evidence: str = "NONE", style: str = "AUTO"):
    return build_policy(
        stage=stage,
        grade=grade,
        preferred_style=style,
        evidence_level=evidence,
        proactive_guidance_enabled=True,
    )


def test_stage_bands_produce_observable_downstream_differences():
    lower = _policy("PRIMARY_LOWER", 2)
    upper = _policy("PRIMARY_UPPER", 4)
    junior = _policy("JUNIOR", 7)
    senior = _policy("SENIOR", 12)

    # quiz volume: 1 / 2 / 3 / 3
    assert [lower.max_quiz_questions, upper.max_quiz_questions] == [1, 2]
    assert junior.max_quiz_questions == senior.max_quiz_questions == 3

    # explanation length grows strictly across the four stages
    lengths = [
        lower.max_explanation_chars,
        upper.max_explanation_chars,
        junior.max_explanation_chars,
        senior.max_explanation_chars,
    ]
    assert lengths == sorted(lengths)
    assert len(set(lengths)) == 4

    # question types and media candidates actually differ downstream
    assert lower.allowed_question_types == ("SINGLE_CHOICE", "TRUE_FALSE")
    assert junior.allowed_question_types == ("SINGLE_CHOICE", "ORDERING")
    assert "ANIMATION" in lower.media_candidates
    assert "CODE" in senior.media_candidates and "CODE" not in lower.media_candidates
    assert lower.scaffolding != senior.scaffolding

    # the same snapshot serialises into the persisted JSONB payload
    assert set(lower.to_snapshot()) == SNAPSHOT_KEYS


def test_expected_stage_boundaries_follow_t05_table():
    expected = {
        1: "PRIMARY_LOWER",
        3: "PRIMARY_LOWER",
        4: "PRIMARY_UPPER",
        6: "PRIMARY_UPPER",
        7: "JUNIOR",
        9: "JUNIOR",
        10: "SENIOR",
        12: "SENIOR",
    }
    for grade, stage in expected.items():
        assert expected_stage_for_grade(grade) == stage
        assert _policy(stage, grade).stage == stage


@pytest.mark.parametrize("bad_grade", [0, 13, "5", True, 1.5, -1])
def test_illegal_grades_are_rejected(bad_grade):
    with pytest.raises(LearningPolicyError):
        expected_stage_for_grade(bad_grade)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("stage", "grade"),
    [("JUNIOR", 2), ("PRIMARY_LOWER", 7), ("SENIOR", 9), ("PRIMARY_UPPER", 12)],
)
def test_stage_grade_conflicts_are_rejected(stage, grade):
    with pytest.raises(LearningPolicyError):
        _policy(stage, grade)
    with pytest.raises(LearningPolicyError):
        build_policy(
            stage=stage,
            grade=grade,
            preferred_style="AUTO",
            evidence_level="NONE",
        )


def test_unknown_stage_style_or_evidence_is_rejected():
    for kwargs in (
        {"stage": "COLLEGE", "grade": None, "preferred_style": "AUTO", "evidence_level": "NONE"},
        {"stage": "JUNIOR", "grade": None, "preferred_style": "HAPTIC", "evidence_level": "NONE"},
        {"stage": "JUNIOR", "grade": None, "preferred_style": "AUTO", "evidence_level": "MASTER"},
    ):
        with pytest.raises(LearningPolicyError):
            build_policy(**kwargs)


def test_null_grade_with_known_stage_still_policies():
    policy = _policy("JUNIOR", None)
    assert policy.grade is None
    assert policy.max_quiz_questions == 3
    assert policy.to_snapshot()["grade"] is None


def test_high_stage_weak_evidence_is_capped_below_hard():
    for level in ("NONE", "EMERGING"):
        policy = _policy("SENIOR", 12, evidence=level)
        assert "HARD" not in policy.allowed_difficulties
        assert policy.allowed_difficulties[-1] == "MEDIUM"
    strong = _policy("SENIOR", 12, evidence="SOLID")
    assert "HARD" in strong.allowed_difficulties
    assert DIFFICULTY_ORDER.index("HARD") > DIFFICULTY_ORDER.index("MEDIUM")


def test_young_stage_never_gets_hard_even_with_solid_evidence():
    policy = _policy("PRIMARY_LOWER", 2, evidence="SOLID")
    assert policy.allowed_difficulties == ("EASY",)


def test_skips_and_reading_time_never_raise_evidence_level():
    assert evidence_level_from(real_activities=0, correct_activities=0) == "NONE"
    assert evidence_level_from(real_activities=0, correct_activities=7) == "NONE"
    assert evidence_level_from(real_activities=1, correct_activities=1) == "EMERGING"
    assert evidence_level_from(real_activities=2, correct_activities=2) == "SOLID"


def test_policy_has_no_ranking_or_personality_surface():
    snapshot = build_policy(
        stage="SENIOR",
        grade=12,
        preferred_style="CODE",
        evidence_level="SOLID",
    ).to_snapshot()
    blob = repr(snapshot).lower()
    for banned in ("rank", "leaderboard", "personality", "iq", "percentile"):
        assert banned not in blob
    assert snapshot["allowed_actions"] == ["TEACH_TURN", "CODE_FEEDBACK"]
