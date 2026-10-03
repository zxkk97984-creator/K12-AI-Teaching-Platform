"""Age-appropriate policy snapshots (QA04/QA06).

The policy is computed from the *real* T05 profile fields (stage, nullable
grade, preferred style) plus the student's stored evidence, and it decides
downstream teaching shape: allowed actions, quiz volume, difficulty ceiling,
question types, explanation length and media candidates.

Rules that matter for acceptance:

* stage/grade consistency reuses the T05 validator (no second boundary table);
* grade ``0``/``13``/strings and stage-mismatched grades are rejected;
* ``grade=None`` with a known stage still produces a full policy;
* a senior student *without* evidence is never pushed to HARD difficulty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.identity.service import IdentityError, _validate_stage_grade

STAGES = ("PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR")
EVIDENCE_LEVELS = ("NONE", "EMERGING", "SOLID")
PREFERRED_STYLES = ("AUTO", "EXAMPLE", "VISUAL", "STORY", "STEP_BY_STEP", "CODE")
DIFFICULTY_ORDER = ("EASY", "MEDIUM", "HARD")


class LearningPolicyError(ValueError):
    """The requested policy inputs are invalid or contradictory."""


@dataclass(frozen=True)
class StageBand:
    max_quiz_questions: int
    difficulties: tuple[str, ...]
    question_types: tuple[str, ...]
    max_explanation_chars: int
    media_candidates: tuple[str, ...]
    scaffolding: str


STAGE_BANDS: dict[str, StageBand] = {
    "PRIMARY_LOWER": StageBand(
        max_quiz_questions=20,
        difficulties=("EASY",),
        question_types=("SINGLE_CHOICE", "TRUE_FALSE"),
        max_explanation_chars=220,
        media_candidates=("FIGURE", "ANIMATION"),
        scaffolding="WARM",
    ),
    "PRIMARY_UPPER": StageBand(
        max_quiz_questions=20,
        difficulties=("EASY", "MEDIUM"),
        question_types=("SINGLE_CHOICE", "TRUE_FALSE", "ORDERING"),
        max_explanation_chars=320,
        media_candidates=("FIGURE", "ANIMATION"),
        scaffolding="WARM",
    ),
    "JUNIOR": StageBand(
        max_quiz_questions=20,
        difficulties=("EASY", "MEDIUM"),
        question_types=("SINGLE_CHOICE", "ORDERING"),
        max_explanation_chars=480,
        media_candidates=("FIGURE", "CODE"),
        scaffolding="GUIDED",
    ),
    "SENIOR": StageBand(
        max_quiz_questions=20,
        difficulties=("EASY", "MEDIUM", "HARD"),
        question_types=("SINGLE_CHOICE", "ORDERING"),
        max_explanation_chars=640,
        media_candidates=("CODE", "FIGURE"),
        scaffolding="CONCISE",
    ),
}

# A high grade never buys a higher difficulty on its own: HARD requires SOLID
# evidence (>= 2 correct real activities). Weak evidence caps at MEDIUM.
DIFFICULTY_CEILING_BY_EVIDENCE = {
    "NONE": "MEDIUM",
    "EMERGING": "MEDIUM",
    "SOLID": "HARD",
}


def expected_stage_for_grade(grade: int) -> str:
    """Derive the stage from the authoritative T05 validator (no duplicate table)."""

    if isinstance(grade, bool) or not isinstance(grade, int):
        raise LearningPolicyError("grade must be an integer or null")
    for stage in STAGES:
        try:
            _validate_stage_grade(stage, grade)
        except IdentityError:
            continue
        return stage
    raise LearningPolicyError("grade must be within 1..12")


@dataclass(frozen=True)
class LearningPolicy:
    stage: str
    grade: int | None
    preferred_style: str
    evidence_level: str
    allowed_actions: tuple[str, ...]
    max_quiz_questions: int
    allowed_difficulties: tuple[str, ...]
    allowed_question_types: tuple[str, ...]
    max_explanation_chars: int
    media_candidates: tuple[str, ...]
    scaffolding: str
    proactive_opening_allowed: bool

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "k12.learning.policy.v1",
            "stage": self.stage,
            "grade": self.grade,
            "preferred_style": self.preferred_style,
            "evidence_level": self.evidence_level,
            "allowed_actions": list(self.allowed_actions),
            "max_quiz_questions": self.max_quiz_questions,
            "allowed_difficulties": list(self.allowed_difficulties),
            "allowed_question_types": list(self.allowed_question_types),
            "max_explanation_chars": self.max_explanation_chars,
            "media_candidates": list(self.media_candidates),
            "scaffolding": self.scaffolding,
            "proactive_opening_allowed": self.proactive_opening_allowed,
        }


def _capped_difficulties(stage: str, evidence_level: str) -> tuple[str, ...]:
    ceiling = DIFFICULTY_CEILING_BY_EVIDENCE[evidence_level]
    allowed = STAGE_BANDS[stage].difficulties
    return tuple(
        item for item in allowed if DIFFICULTY_ORDER.index(item) <= DIFFICULTY_ORDER.index(ceiling)
    )


def build_policy(
    *,
    stage: str | None,
    grade: int | None,
    preferred_style: str,
    evidence_level: str,
    proactive_guidance_enabled: bool = True,
) -> LearningPolicy:
    if stage not in STAGES:
        raise LearningPolicyError("stage must be one of the four stages")
    if evidence_level not in EVIDENCE_LEVELS:
        raise LearningPolicyError("evidence_level is not recognised")
    if preferred_style not in PREFERRED_STYLES:
        raise LearningPolicyError("preferred_style is not recognised")
    if grade is not None:
        # Reuse the T05 rule: rejects 0/13/strings and stage/grade mismatches.
        if isinstance(grade, bool) or not isinstance(grade, int):
            raise LearningPolicyError("grade must be an integer or null")
        try:
            _validate_stage_grade(stage, grade)
        except IdentityError as exc:
            raise LearningPolicyError(str(exc)) from exc

    band = STAGE_BANDS[stage]
    return LearningPolicy(
        stage=stage,
        grade=grade,
        preferred_style=preferred_style,
        evidence_level=evidence_level,
        allowed_actions=("TEACH_TURN", "CODE_FEEDBACK"),
        max_quiz_questions=band.max_quiz_questions,
        allowed_difficulties=_capped_difficulties(stage, evidence_level),
        allowed_question_types=band.question_types,
        max_explanation_chars=band.max_explanation_chars,
        media_candidates=band.media_candidates,
        scaffolding=band.scaffolding,
        proactive_opening_allowed=proactive_guidance_enabled,
    )


def evidence_level_from(*, real_activities: int, correct_activities: int) -> str:
    """Skips and reading time never count; only real activities do."""

    if real_activities <= 0:
        return "NONE"
    if correct_activities < 2:
        return "EMERGING"
    return "SOLID"
