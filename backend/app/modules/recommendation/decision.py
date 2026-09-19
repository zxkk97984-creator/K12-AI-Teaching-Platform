"""The one next-step decision (T19 L1–L4/L8).

Both the recommendation API and the teaching side are derived from this single
function and from the *same* stored teaching state (``teaching_lesson_sessions``
phase/lifecycle). It is a pure function: given the same inputs it returns the
same decision, so a page cannot tell the student "continue the quiz" while the
lesson says something else.

Design rules (``k12.recommendation.rule.v1`` — a local design rule, **not** a
validated teaching effect):

1. an unfinished lesson the student already owns wins;
2. a real wrong answer that was never corrected wins over new content;
3. otherwise keep practising an objective that is still forming;
4. otherwise continue the course catalogue in order;
5. cold start (no real evidence) starts from the catalogue and says so.

Hints, skips and reading time are never treated as mastery, and the decision
never raises difficulty: it has no difficulty field at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

RULE_VERSION = "k12.recommendation.rule.v1"
THRESHOLDS_VERSION = "k12.recommendation.thresholds.v1"
# These are local design rules; no teaching effect has been verified (QA20).
EFFECT_VERIFIED = False

KIND_CONTINUE_LESSON = "CONTINUE_LESSON"
KIND_REVIEW_MISTAKE = "REVIEW_MISTAKE"
KIND_PRACTICE_WEAK = "PRACTICE_WEAK"
KIND_CONTINUE_COURSE = "CONTINUE_COURSE"
KIND_START_COURSE = "START_COURSE"
KIND_INTEREST_MATCH = "INTEREST_MATCH"
KIND_NO_CONTENT = "NO_CONTENT"
KIND_ALL_IGNORED = "ALL_IGNORED"

PHASE_ADVICE: dict[str, dict[str, str]] = {
    "ORIENT": {"title": "开始这一节的讲解", "reason": "这一节还没开始讲解。"},
    "EXPLAIN": {"title": "看完讲解，进入检查", "reason": "这一节正在讲解阶段。"},
    "CHECK": {"title": "完成本节的理解检查", "reason": "这一节正在检查阶段。"},
    "PRACTICE": {"title": "完成这一节的练习", "reason": "这一节正在练习阶段。"},
    "REFLECT": {"title": "复盘并结束本节", "reason": "这一节在复盘阶段。"},
}


@dataclass(frozen=True)
class LessonState:
    session_id: str
    chapter_id: str
    chapter_title: str
    phase: str
    lifecycle: str
    policy_snapshot_id: str | None = None


@dataclass(frozen=True)
class ObjectiveState:
    objective_id: str
    answered: int
    incorrect: int
    level: str  # T18 observation level: EMERGING / CONSISTENT
    last_incorrect_evidence_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateChapter:
    chapter_id: str
    title: str
    course_title: str
    order_index: int
    stage: str
    knowledge_point_slugs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionInputs:
    stage: str
    grade: int | None
    preferred_style: str
    interests: tuple[str, ...] = ()
    active_lesson: LessonState | None = None
    objectives: tuple[ObjectiveState, ...] = ()
    candidates: tuple[CandidateChapter, ...] = ()
    completed_chapter_ids: tuple[str, ...] = ()
    active_memory_ids: tuple[str, ...] = ()
    real_answers: int = 0
    hints_or_skips_only: bool = False
    ignored_subjects: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def _item(
    *,
    kind: str,
    subject_key: str,
    title: str,
    reason: str,
    source: dict[str, Any],
    evidence_ids: list[str] | None = None,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "subject_key": subject_key,
        "title": title,
        "reason": reason,
        "source": source,
        "evidence_ids": list(evidence_ids or []),
        "action": action or {},
        "rule_version": RULE_VERSION,
        "thresholds_version": THRESHOLDS_VERSION,
        "effect_verified": EFFECT_VERIFIED,
    }


def _weakest(objectives: tuple[ObjectiveState, ...]) -> ObjectiveState | None:
    """Deterministic: most wrong answers first, then objective id."""

    with_answers = [item for item in objectives if item.answered > 0]
    if not with_answers:
        return None
    return sorted(with_answers, key=lambda item: (-item.incorrect, item.objective_id))[0]


def _interest_match(inputs: DecisionInputs) -> CandidateChapter | None:
    if not inputs.interests:
        return None
    terms = tuple(term.strip().lower() for term in inputs.interests if term.strip())
    for candidate in sorted(inputs.candidates, key=lambda item: item.order_index):
        haystack = " ".join(
            (candidate.title, candidate.course_title, *candidate.knowledge_point_slugs)
        ).lower()
        if any(term and term in haystack for term in terms):
            return candidate
    return None


def _course_candidate(inputs: DecisionInputs) -> CandidateChapter | None:
    done = set(inputs.completed_chapter_ids)
    for candidate in sorted(inputs.candidates, key=lambda item: item.order_index):
        if candidate.chapter_id not in done:
            return candidate
    return None


def decide_next_step(inputs: DecisionInputs) -> dict[str, Any]:
    """Pure decision. Same inputs ⇒ same output, no I/O."""

    ignored = set(inputs.ignored_subjects)
    alternatives: list[dict[str, Any]] = []

    lesson = inputs.active_lesson
    if lesson is not None and lesson.lifecycle in ("ACTIVE", "PAUSED"):
        advice = PHASE_ADVICE.get(lesson.phase, PHASE_ADVICE["ORIENT"])
        paused = lesson.lifecycle == "PAUSED"
        primary = _item(
            kind=KIND_CONTINUE_LESSON,
            subject_key=f"lesson:{lesson.session_id}",
            title="继续之前暂停的这一节" if paused else advice["title"],
            reason=(
                "这一节被你暂停了，随时可以继续。"
                if paused
                else f"{advice['reason']}课堂里显示的是同一个下一步。"
            ),
            source={
                "type": "LESSON_SESSION",
                "session_id": lesson.session_id,
                "chapter_id": lesson.chapter_id,
                "chapter_title": lesson.chapter_title,
                "phase": lesson.phase,
                "lifecycle": lesson.lifecycle,
            },
            action={
                "type": "OPEN_LESSON",
                "session_id": lesson.session_id,
                "phase": lesson.phase,
            },
        )
    else:
        weak = _weakest(inputs.objectives)
        if weak is not None and weak.incorrect > 0 and weak.level != "CONSISTENT":
            primary = _item(
                kind=KIND_REVIEW_MISTAKE,
                subject_key=f"objective:{weak.objective_id}",
                title="先复盘错题，再做一组同类练习",
                reason=(
                    f"这个目标有 {weak.incorrect} 次真实答错、还没有完全改正；"
                    "下一步先看解析再练，不会直接加难度。"
                ),
                source={"type": "OBJECTIVE", "objective_id": weak.objective_id},
                evidence_ids=list(weak.evidence_ids),
                action={"type": "OPEN_PRACTICE", "objective_id": weak.objective_id},
            )
        elif weak is not None and weak.level != "CONSISTENT":
            primary = _item(
                kind=KIND_PRACTICE_WEAK,
                subject_key=f"objective:{weak.objective_id}",
                title="继续练习这个目标",
                reason=(
                    f"这个目标已经看到 {weak.answered} 次真实作答，还在形成中；"
                    "多练几次比直接进入新内容更稳。"
                ),
                source={"type": "OBJECTIVE", "objective_id": weak.objective_id},
                evidence_ids=list(weak.evidence_ids),
                action={"type": "OPEN_PRACTICE", "objective_id": weak.objective_id},
            )
        else:
            candidate = _course_candidate(inputs)
            if candidate is None:
                primary = _item(
                    kind=KIND_NO_CONTENT,
                    subject_key="content:none",
                    title="当前没有可用的已发布章节",
                    reason="你的学段暂时没有已发布且适龄的章节，老师会在内容发布后再推荐。",
                    source={"type": "CATALOGUE", "stage": inputs.stage},
                )
            elif inputs.real_answers == 0 and not inputs.completed_chapter_ids:
                primary = _item(
                    kind=KIND_START_COURSE,
                    subject_key=f"chapter:{candidate.chapter_id}",
                    title=f"从《{candidate.title}》开始",
                    reason=(
                        "还没有你的真实学习记录，这是按学段和课程目录给出的起点，"
                        "不是根据已学历史推断的；学过之后建议会随真实证据变化。"
                    ),
                    source={
                        "type": "CHAPTER",
                        "chapter_id": candidate.chapter_id,
                        "course_title": candidate.course_title,
                    },
                    action={"type": "OPEN_CHAPTER", "chapter_id": candidate.chapter_id},
                )
            else:
                primary = _item(
                    kind=KIND_CONTINUE_COURSE,
                    subject_key=f"chapter:{candidate.chapter_id}",
                    title=f"接着学《{candidate.title}》",
                    reason="这一章在你的课程顺序里还没完成，而且是已发布、适龄的内容。",
                    source={
                        "type": "CHAPTER",
                        "chapter_id": candidate.chapter_id,
                        "course_title": candidate.course_title,
                    },
                    action={"type": "OPEN_CHAPTER", "chapter_id": candidate.chapter_id},
                )

    # Interest match is an alternative, never a competing primary.
    interest = _interest_match(inputs)
    if interest is not None and f"chapter:{interest.chapter_id}" != primary["subject_key"]:
        alternatives.append(
            _item(
                kind=KIND_INTEREST_MATCH,
                subject_key=f"chapter:{interest.chapter_id}",
                title=f"和你写的兴趣有关：《{interest.title}》",
                reason="匹配你填写的学习兴趣，属于可选内容，不会覆盖上面这一步。",
                source={
                    "type": "CHAPTER",
                    "chapter_id": interest.chapter_id,
                    "course_title": interest.course_title,
                },
                action={"type": "OPEN_CHAPTER", "chapter_id": interest.chapter_id},
            )
        )

    # Ignored subjects never come back until the student restores them.
    if primary is not None and primary["subject_key"] in ignored:
        remaining = [item for item in alternatives if item["subject_key"] not in ignored]
        if remaining:
            primary = remaining.pop(0)
        else:
            primary = _item(
                kind=KIND_ALL_IGNORED,
                subject_key="recommendation:all-ignored",
                title="你已经忽略了目前的建议",
                reason="这里没有其它可推荐的下一步了；可以在下面恢复被忽略的建议。",
                source={"type": "STUDENT_FEEDBACK"},
            )
    alternatives = [
        item
        for item in alternatives
        if item["subject_key"] != primary["subject_key"] and item["subject_key"] not in ignored
    ]

    basis = {
        "stage": inputs.stage,
        "grade": inputs.grade,
        "preferred_style": inputs.preferred_style,
        "active_lesson_id": inputs.active_lesson.session_id if inputs.active_lesson else None,
        "active_phase": inputs.active_lesson.phase if inputs.active_lesson else None,
        "real_answers": inputs.real_answers,
        "hints_or_skips_only": inputs.hints_or_skips_only,
        "objective_count": len(inputs.objectives),
        "candidate_count": len(inputs.candidates),
        "completed_chapter_count": len(inputs.completed_chapter_ids),
        "active_memory_ids": list(inputs.active_memory_ids),
        "evidence_ids": sorted(set(inputs.evidence_ids)),
        "rule_version": RULE_VERSION,
        "thresholds_version": THRESHOLDS_VERSION,
        "effect_verified": EFFECT_VERIFIED,
        "ignored_subjects": sorted(ignored),
    }
    return {
        "primary": primary,
        "alternatives": alternatives,
        "basis": basis,
        "rule_version": RULE_VERSION,
        "thresholds_version": THRESHOLDS_VERSION,
        "effect_verified": EFFECT_VERIFIED,
        "honest_notes": [
            "这是按设计规则给出的下一步，不是经过实证验证的教学效果。",
            "提示、跳过和阅读时长都不算掌握；证据不足时会直接说明。",
            "没有排行榜，也不会给出掌握度百分比或人格/智力推断。",
        ],
    }


def inputs_hash(inputs: DecisionInputs) -> str:
    """Stable fingerprint of the material inputs (no timestamps, no ids of runs)."""

    payload = {
        "stage": inputs.stage,
        "grade": inputs.grade,
        "preferred_style": inputs.preferred_style,
        "interests": list(inputs.interests),
        "active_lesson": (
            {
                "session_id": inputs.active_lesson.session_id,
                "phase": inputs.active_lesson.phase,
                "lifecycle": inputs.active_lesson.lifecycle,
            }
            if inputs.active_lesson
            else None
        ),
        "objectives": [
            {
                "id": item.objective_id,
                "answered": item.answered,
                "incorrect": item.incorrect,
                "level": item.level,
                "evidence_ids": sorted(item.evidence_ids),
            }
            for item in sorted(inputs.objectives, key=lambda entry: entry.objective_id)
        ],
        "candidates": [
            {"id": item.chapter_id, "order": item.order_index}
            for item in sorted(inputs.candidates, key=lambda entry: entry.chapter_id)
        ],
        "completed": sorted(inputs.completed_chapter_ids),
        "memories": sorted(inputs.active_memory_ids),
        "real_answers": inputs.real_answers,
        "hints_or_skips_only": inputs.hints_or_skips_only,
        "ignored": sorted(inputs.ignored_subjects),
        "rule_version": RULE_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
