"""Evidence projection and versioned qualitative observations (T18 K1/K3/K4/K7/K8).

Trusted sources stay authoritative:

* ``learning_quiz_evidence`` — written inside the quiz attempt/hint transaction;
* ``learning_evidence`` — written by legal local lesson events.

This module only *projects* them: every projected row carries a stable
``dedup_key`` (source kind + source event id) plus the original source
reference, so re-projecting is idempotent and any projected fact can be traced
back to the question/activity it came from.

Observations are qualitative statements derived from the projected items. They
are fingerprinted, never overwritten (a changed basis supersedes the previous
version) and deliberately contain **no mastery percentage**: the levels are
``INSUFFICIENT_EVIDENCE`` / ``EMERGING`` / ``CONSISTENT`` with the raw counts and
the rule version attached. A read-only API never creates a projection.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import (
    CORRECT_OUTCOMES,
    EvidenceItem,
    LearningEvidence,
    Observation,
    QuizEvidence,
)

EVIDENCE_RULE_VERSION = "k12.evidence.projection.v1"
OBSERVATION_RULE_VERSION = "k12.observation.rule.v1"
OBSERVATION_THRESHOLDS_VERSION = "k12.observation.thresholds.v1"
# The local rules are not validated teaching-effect claims (QA20).
OBSERVATION_EFFECT_VERIFIED = False

_TEACHING_KIND = {
    "QUIZ_ANSWERED": "QUIZ_RESULT",
    "QUIZ_HINT_VIEWED": "QUIZ_RESULT",
    "QUIZ_REVIEW_LINKED": "QUIZ_RESULT",
    "QUIZ_SESSION_COMPLETED": "QUIZ_RESULT",
    "LESSON_ACTIVITY": "LEARNING_ACTIVITY",
}


def dedup_key(*, source: str, kind: str, event_id: uuid.UUID) -> str:
    return f"{source}:{kind}:{event_id}"[:96]


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


MAX_REQUEST_EVIDENCE = 12


def merge_learner_context(
    context: dict[str, Any], learner_context: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """Attach this run's valid evidence and ACTIVE memories (T18 K3).

    The frozen teaching-request contract has no separate memory field and sets
    ``additionalProperties: false``, so learner facts travel in the existing
    ``evidence`` array (kinds ``QUIZ_RESULT`` / ``LEARNING_ACTIVITY`` /
    ``CONFIRMED_MEMORY``). Only the ids actually injected become citable: the
    run-local context copy is extended, so response validation keeps rejecting
    anything the model invents. The teaching request builder itself stays
    untouched (it is an approved-scope boundary for this card).
    """

    merged: dict[str, dict[str, str]] = {}
    # The account's current personal note must survive the request's evidence
    # cap even when a lesson carries many quiz or activity observations.
    for item in learner_context or []:
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id.startswith("memory-document:"):
            merged[item_id] = {
                "id": item_id[:160],
                "kind": str(item.get("kind") or "CONFIRMED_MEMORY"),
                "summary": str(item.get("summary") or "")[:1200],
            }
    for item in context.get("evidence") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            merged.setdefault(item["id"], item)
    for item in learner_context or []:
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            merged[item_id] = {
                "id": item_id[:160],
                "kind": str(item.get("kind") or "LEARNING_ACTIVITY"),
                "summary": str(item.get("summary") or "")[:1200],
            }
    injected = list(merged.values())[:MAX_REQUEST_EVIDENCE]
    allowed = list(dict.fromkeys(list(context.get("allowed_evidence_ids") or [])))
    for item in injected:
        if item["id"] not in allowed:
            allowed.append(item["id"])
    context["allowed_evidence_ids"] = allowed
    return injected


def evidence_summary_text(item: EvidenceItem) -> str:
    """One honest sentence about a projected fact (never a mastery claim)."""

    target = f"目标「{item.objective_id}」" if item.objective_id else "本章活动"
    ref = item.source_ref or {}
    if item.source_kind == "QUIZ_ANSWERED":
        verdict = "答对" if item.outcome in CORRECT_OUTCOMES else "答错"
        question = str(ref.get("question_id", ""))[:8]
        return f"题目作答：{verdict} · {target} · 题目 {question}"
    if item.source_kind == "QUIZ_HINT_VIEWED":
        return f"查看了提示（不计为答对）· {target}"
    if item.source_kind == "QUIZ_REVIEW_LINKED":
        return f"答错后生成了复习建议 · {target}"
    if item.source_kind == "QUIZ_SESSION_COMPLETED":
        return f"完成了一组练习 · {target}"
    return f"课堂活动：{item.outcome} · {target}"


async def _insert_item(db: AsyncSession, values: dict[str, Any]) -> bool:
    statement = (
        pg_insert(EvidenceItem)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(EvidenceItem.id)
    )
    return await db.scalar(statement) is not None


async def project_evidence(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 200
) -> dict[str, int]:
    """Project trusted events into the deduplicated evidence read model."""

    quiz_rows = (
        await db.scalars(
            select(QuizEvidence)
            .where(QuizEvidence.owner_user_id == owner_user_id)
            .order_by(QuizEvidence.created_at.desc())
            .limit(limit)
        )
    ).all()
    lesson_rows = (
        await db.scalars(
            select(LearningEvidence)
            .where(LearningEvidence.owner_user_id == owner_user_id)
            .order_by(LearningEvidence.created_at.desc())
            .limit(limit)
        )
    ).all()

    inserted = 0
    for row in quiz_rows:
        values = {
            "owner_user_id": owner_user_id,
            "source_kind": row.kind,
            "source_event_id": row.source_event_id,
            "dedup_key": dedup_key(source="quiz", kind=row.kind, event_id=row.source_event_id),
            "outcome": row.outcome,
            "objective_id": row.objective_id,
            "knowledge_point_slugs": list(row.knowledge_point_slugs or []),
            "source_ref": {
                "quiz_session_id": str(row.quiz_session_id),
                "question_id": str(row.question_id) if row.question_id else None,
                "thresholds_version": row.thresholds_version,
                "source": "learning_quiz_evidence",
            },
            "projection_rule_version": EVIDENCE_RULE_VERSION,
            "observed_at": row.created_at,
        }
        if await _insert_item(db, values):
            inserted += 1

    for row in lesson_rows:
        values = {
            "owner_user_id": owner_user_id,
            "source_kind": "LESSON_ACTIVITY",
            "source_event_id": row.id,
            "dedup_key": dedup_key(source="lesson", kind=row.kind, event_id=row.id),
            "outcome": row.outcome,
            "objective_id": None,
            "knowledge_point_slugs": [],
            "source_ref": {
                "lesson_session_id": str(row.session_id),
                "lesson_event_kind": row.kind,
                "reference": row.reference,
                "source": "learning_evidence",
            },
            "projection_rule_version": EVIDENCE_RULE_VERSION,
            "observed_at": row.created_at,
        }
        if await _insert_item(db, values):
            inserted += 1

    await db.commit()
    return {
        "scanned": len(quiz_rows) + len(lesson_rows),
        "inserted": inserted,
        "rule_version": EVIDENCE_RULE_VERSION,
    }


async def needs_projection(db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 200) -> bool:
    """True when a trusted event exists that has not been projected yet."""

    quiz_keys = [
        dedup_key(source="quiz", kind=kind, event_id=event_id)
        for kind, event_id in (
            await db.execute(
                select(QuizEvidence.kind, QuizEvidence.source_event_id)
                .where(QuizEvidence.owner_user_id == owner_user_id)
                .order_by(QuizEvidence.created_at.desc())
                .limit(limit)
            )
        ).all()
    ]
    lesson_keys = [
        dedup_key(source="lesson", kind=kind, event_id=event_id)
        for kind, event_id in (
            await db.execute(
                select(LearningEvidence.kind, LearningEvidence.id)
                .where(LearningEvidence.owner_user_id == owner_user_id)
                .order_by(LearningEvidence.created_at.desc())
                .limit(limit)
            )
        ).all()
    ]
    expected = set(quiz_keys) | set(lesson_keys)
    if not expected:
        return False
    known = set(
        await db.scalars(select(EvidenceItem.dedup_key).where(EvidenceItem.dedup_key.in_(expected)))
    )
    return bool(expected - known)


def _level(answered: int, correct: int) -> str:
    if answered <= 0:
        return "INSUFFICIENT_EVIDENCE"
    if answered >= 2 and correct >= 2:
        return "CONSISTENT"
    return "EMERGING"


def _statement(*, objective: str, level: str, answered: int, correct: int, questions: int) -> str:
    head = f"目标「{objective}」："
    if level == "INSUFFICIENT_EVIDENCE":
        return head + "目前没有针对这个目标的真实作答记录；仍需观察，暂不下结论。"
    if level == "CONSISTENT":
        return (
            f"{head}已看到 {answered} 次真实作答（{correct} 次答对，覆盖 {questions} 道不同题），"
            "多次答对且跨题出现；按规则记为「较一致」。这是本地定性观察，不是官方掌握度评分。"
        )
    return (
        f"{head}已看到 {answered} 次真实作答（{correct} 次答对，覆盖 {questions} 道不同题）；"
        "证据还在累积，仍在形成中，建议继续观察。"
    )


async def rebuild_observations(db: AsyncSession, *, owner_user_id: uuid.UUID) -> dict[str, int]:
    """Recompute the current qualitative observation per objective (versioned)."""

    answer_items = (
        await db.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.owner_user_id == owner_user_id,
                EvidenceItem.source_kind == "QUIZ_ANSWERED",
            )
            .order_by(EvidenceItem.observed_at)
        )
    ).all()
    hint_items = (
        await db.scalars(
            select(EvidenceItem).where(
                EvidenceItem.owner_user_id == owner_user_id,
                EvidenceItem.source_kind == "QUIZ_HINT_VIEWED",
            )
        )
    ).all()
    hints_by_objective: dict[str, int] = {}
    for item in hint_items:
        if item.objective_id:
            hints_by_objective[item.objective_id] = hints_by_objective.get(item.objective_id, 0) + 1

    grouped: dict[str, list[EvidenceItem]] = {}
    for item in answer_items:
        if item.objective_id:
            grouped.setdefault(item.objective_id, []).append(item)

    created = 0
    reused = 0
    for objective, items in sorted(grouped.items()):
        answered = len(items)
        correct = len([item for item in items if item.outcome in CORRECT_OUTCOMES])
        question_ids = {
            str((item.source_ref or {}).get("question_id"))
            for item in items
            if (item.source_ref or {}).get("question_id")
        }
        level = _level(answered, correct)
        basis = {
            "evidence_ids": [str(item.id) for item in items],
            "hint_evidence_ids": [
                str(item.id) for item in hint_items if item.objective_id == objective
            ],
            "answered": answered,
            "correct": correct,
            "distinct_questions": len(question_ids),
            "hints_viewed": hints_by_objective.get(objective, 0),
            "rule_version": OBSERVATION_RULE_VERSION,
            "thresholds_version": OBSERVATION_THRESHOLDS_VERSION,
            "effect_verified": OBSERVATION_EFFECT_VERIFIED,
        }
        fingerprint = _fingerprint(
            {
                "subject": objective,
                "level": level,
                "evidence_ids": sorted(basis["evidence_ids"]),
                "rule_version": OBSERVATION_RULE_VERSION,
            }
        )
        existing = await db.scalar(
            select(Observation).where(
                Observation.owner_user_id == owner_user_id,
                Observation.subject_key == objective,
                Observation.observation_rule_version == OBSERVATION_RULE_VERSION,
                Observation.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            # Same facts, same rule: re-projecting must not create a new version.
            reused += 1
            continue

        current = await db.scalar(
            select(Observation)
            .where(
                Observation.owner_user_id == owner_user_id,
                Observation.subject_key == objective,
                Observation.superseded_at.is_(None),
            )
            .order_by(Observation.projection_revision.desc())
        )
        next_revision = (
            int(
                await db.scalar(
                    select(func.coalesce(func.max(Observation.projection_revision), 0)).where(
                        Observation.owner_user_id == owner_user_id,
                        Observation.subject_key == objective,
                    )
                )
                or 0
            )
            + 1
        )
        if current is not None:
            current.superseded_at = datetime.now(UTC)
        db.add(
            Observation(
                owner_user_id=owner_user_id,
                subject_kind="OBJECTIVE",
                subject_key=objective,
                level=level,
                statement=_statement(
                    objective=objective,
                    level=level,
                    answered=answered,
                    correct=correct,
                    questions=len(question_ids),
                ),
                basis=basis,
                observation_rule_version=OBSERVATION_RULE_VERSION,
                fingerprint=fingerprint,
                projection_revision=next_revision,
            )
        )
        created += 1

    await db.commit()
    return {
        "objectives": len(grouped),
        "created": created,
        "reused": reused,
        "rule_version": OBSERVATION_RULE_VERSION,
    }


async def project_and_observe(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 200
) -> dict[str, Any]:
    """Event-triggered (worker/explicit) projection; read APIs never call it."""

    evidence = await project_evidence(db, owner_user_id=owner_user_id, limit=limit)
    observations = await rebuild_observations(db, owner_user_id=owner_user_id)
    return {"evidence": evidence, "observations": observations}


async def current_observations(db: AsyncSession, *, owner_user_id: uuid.UUID) -> list[Observation]:
    rows = await db.scalars(
        select(Observation)
        .where(Observation.owner_user_id == owner_user_id, Observation.superseded_at.is_(None))
        .order_by(Observation.subject_key)
    )
    return list(rows)


def observation_dto(row: Observation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "subject_kind": row.subject_kind,
        "subject_key": row.subject_key,
        "level": row.level,
        "statement": row.statement,
        "basis": dict(row.basis or {}),
        "rule_version": row.observation_rule_version,
        "projection_revision": row.projection_revision,
        "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None,
        "created_at": row.created_at.isoformat(),
        "notice": "本地定性观察；不是掌握度百分比，也未验证教学效果。",
    }


async def evidence_context(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 6
) -> list[dict[str, str]]:
    """Newest valid evidence as contract-shaped items (ids the run may cite)."""

    rows = (
        await db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.owner_user_id == owner_user_id)
            .order_by(EvidenceItem.observed_at.desc())
            .limit(max(limit, 0))
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "kind": _TEACHING_KIND.get(row.source_kind, "LEARNING_ACTIVITY"),
            "summary": evidence_summary_text(row)[:1200],
        }
        for row in rows
    ]


async def growth_overview(db: AsyncSession, *, owner_user_id: uuid.UUID) -> dict[str, Any]:
    """Owner-scoped read model for the growth page (no writes here)."""

    items = (
        await db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.owner_user_id == owner_user_id)
            .order_by(EvidenceItem.observed_at.desc())
        )
    ).all()
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item.source_kind] = by_kind.get(item.source_kind, 0) + 1
    answers = [item for item in items if item.source_kind == "QUIZ_ANSWERED"]
    correct = len([item for item in answers if item.outcome in CORRECT_OUTCOMES])
    observations = await current_observations(db, owner_user_id=owner_user_id)

    return {
        "owner_scoped": True,
        "evidence_total": len(items),
        "evidence_by_kind": by_kind,
        "real_answers": len(answers),
        "correct_answers": correct,
        "observations": [observation_dto(row) for row in observations],
        "insufficient_evidence": len(answers) < 2,
        "counts_not_effect_notice": (
            "记录条数只是本地记录，不代表学习效果；证据不足时会明确写「仍需观察」。"
        ),
        "no_percentage_notice": "本页不生成掌握度百分比，也不推断智力或性格。",
    }


async def evidence_detail(
    db: AsyncSession, *, owner_user_id: uuid.UUID, evidence_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await db.scalar(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id, EvidenceItem.owner_user_id == owner_user_id
        )
    )
    if row is None:
        return None
    return {
        "id": str(row.id),
        "source_kind": row.source_kind,
        "outcome": row.outcome,
        "objective_id": row.objective_id,
        "knowledge_point_slugs": list(row.knowledge_point_slugs or []),
        "source_ref": dict(row.source_ref or {}),
        "rule_version": row.projection_rule_version,
        "observed_at": row.observed_at.isoformat(),
        "projected_at": row.projected_at.isoformat(),
        "summary": evidence_summary_text(row),
    }
