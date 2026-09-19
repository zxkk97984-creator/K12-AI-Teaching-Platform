"""Phase vs lifecycle, driven by one explicit transition table (F1/F6/F7/F9).

``phase`` is the pedagogical position (ORIENT → EXPLAIN → CHECK → PRACTICE →
REFLECT → COMPLETED). ``lifecycle`` is the student-facing session state
(ACTIVE / PAUSED / COMPLETED / STALE) and is independent: pausing never moves
the phase, and a phase move never flips the lifecycle on its own.

Only *local legal events* move the phase. A tutor's ``phase_suggestion`` is
stored as a suggestion; it can never write COMPLETED, and it never writes a
score. Completion requires a real activity (not scrolling, not a model claim)
plus an explicit student COMPLETE_REQUESTED event.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modules.learning.models import (
    CORRECT_OUTCOMES,
    REAL_ACTIVITY_KINDS,
)


class Phase(StrEnum):
    ORIENT = "ORIENT"
    EXPLAIN = "EXPLAIN"
    CHECK = "CHECK"
    PRACTICE = "PRACTICE"
    REFLECT = "REFLECT"
    COMPLETED = "COMPLETED"


class Lifecycle(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STALE = "STALE"


class LessonEvent(StrEnum):
    ENTER = "ENTER"
    RESUME = "RESUME"
    ASK = "ASK"
    START_EXPLAIN = "START_EXPLAIN"
    EXPLAIN_DONE = "EXPLAIN_DONE"
    CHECK_CORRECT = "CHECK_CORRECT"
    CHECK_INCORRECT = "CHECK_INCORRECT"
    PRACTICE_DONE = "PRACTICE_DONE"
    SKIP_ACTIVITY = "SKIP_ACTIVITY"
    REFLECT_DONE = "REFLECT_DONE"
    COMPLETE_REQUESTED = "COMPLETE_REQUESTED"
    PAUSE = "PAUSE"
    RESUME_FROM_PAUSE = "RESUME_FROM_PAUSE"


class IllegitimateTransition(Exception):
    """The event is not legal from the current phase/lifecycle."""


@dataclass(frozen=True)
class Transition:
    from_phases: tuple[Phase, ...]
    to_phase: Phase | None  # None = phase unchanged
    lifecycle: Lifecycle | None  # None = lifecycle unchanged
    evidence: tuple[str, str] | None = None  # (kind, outcome)
    requires_real_activity: bool = False
    triggers_tutor: bool = False


TRANSITIONS: dict[LessonEvent, Transition] = {
    LessonEvent.ENTER: Transition(
        from_phases=tuple(Phase), to_phase=None, lifecycle=None, triggers_tutor=True
    ),
    LessonEvent.RESUME: Transition(
        from_phases=tuple(Phase), to_phase=None, lifecycle=Lifecycle.ACTIVE
    ),
    LessonEvent.ASK: Transition(
        from_phases=tuple(Phase), to_phase=None, lifecycle=None, triggers_tutor=True
    ),
    LessonEvent.START_EXPLAIN: Transition(
        from_phases=(Phase.ORIENT, Phase.EXPLAIN),
        to_phase=Phase.EXPLAIN,
        lifecycle=Lifecycle.ACTIVE,
    ),
    LessonEvent.EXPLAIN_DONE: Transition(
        from_phases=(Phase.EXPLAIN,), to_phase=Phase.CHECK, lifecycle=Lifecycle.ACTIVE
    ),
    LessonEvent.CHECK_CORRECT: Transition(
        from_phases=(Phase.CHECK,),
        to_phase=Phase.PRACTICE,
        lifecycle=Lifecycle.ACTIVE,
        evidence=("QUIZ_ANSWERED", "CORRECT"),
    ),
    LessonEvent.CHECK_INCORRECT: Transition(
        from_phases=(Phase.CHECK,),
        to_phase=Phase.CHECK,
        lifecycle=Lifecycle.ACTIVE,
        evidence=("QUIZ_ANSWERED", "INCORRECT"),
    ),
    LessonEvent.PRACTICE_DONE: Transition(
        from_phases=(Phase.PRACTICE,),
        to_phase=Phase.REFLECT,
        lifecycle=Lifecycle.ACTIVE,
        evidence=("PRACTICE_COMPLETED", "COMPLETED"),
    ),
    LessonEvent.SKIP_ACTIVITY: Transition(
        from_phases=(Phase.EXPLAIN, Phase.CHECK, Phase.PRACTICE),
        to_phase=None,
        lifecycle=Lifecycle.ACTIVE,
        evidence=("ACTIVITY_SKIPPED", "SKIPPED"),
    ),
    LessonEvent.REFLECT_DONE: Transition(
        from_phases=(Phase.REFLECT,),
        to_phase=Phase.REFLECT,
        lifecycle=Lifecycle.ACTIVE,
        evidence=("REFLECTION_SUBMITTED", "SUBMITTED"),
    ),
    LessonEvent.COMPLETE_REQUESTED: Transition(
        from_phases=(Phase.ORIENT, Phase.EXPLAIN, Phase.CHECK, Phase.PRACTICE, Phase.REFLECT),
        to_phase=Phase.COMPLETED,
        lifecycle=Lifecycle.COMPLETED,
        requires_real_activity=True,
    ),
    LessonEvent.PAUSE: Transition(
        from_phases=tuple(Phase), to_phase=None, lifecycle=Lifecycle.PAUSED
    ),
    LessonEvent.RESUME_FROM_PAUSE: Transition(
        from_phases=tuple(Phase), to_phase=None, lifecycle=Lifecycle.ACTIVE
    ),
}

TUTOR_TRIGGERING_EVENTS = tuple(
    event for event, transition in TRANSITIONS.items() if transition.triggers_tutor
)
PAUSABLE_LIFECYCLES = (Lifecycle.ACTIVE, Lifecycle.PAUSED)


def resolve_event(event: LessonEvent, *, phase: Phase, lifecycle: Lifecycle) -> Transition:
    transition = TRANSITIONS.get(event)
    if transition is None:
        raise IllegitimateTransition(f"unknown lesson event: {event}")
    if phase not in transition.from_phases:
        raise IllegitimateTransition(f"{event.value} is not legal from phase {phase.value}")
    if lifecycle is Lifecycle.COMPLETED:
        raise IllegitimateTransition("completed sessions are read-only")
    if lifecycle is Lifecycle.STALE:
        raise IllegitimateTransition("stale sessions cannot advance")
    if lifecycle is Lifecycle.PAUSED and event not in (
        LessonEvent.RESUME,
        LessonEvent.RESUME_FROM_PAUSE,
    ):
        # Pausing is a real stop: nothing advances until the student resumes.
        raise IllegitimateTransition("session is paused")
    if event is LessonEvent.RESUME_FROM_PAUSE and lifecycle is not Lifecycle.PAUSED:
        raise IllegitimateTransition("session is not paused")
    if event is LessonEvent.PAUSE and lifecycle is Lifecycle.PAUSED:
        raise IllegitimateTransition("session is already paused")
    return transition


def real_activity_kinds() -> tuple[str, ...]:
    return REAL_ACTIVITY_KINDS


def is_correct_outcome(kind: str, outcome: str) -> bool:
    return kind in REAL_ACTIVITY_KINDS and outcome in CORRECT_OUTCOMES


def completion_allowed(*, real_activities: int) -> bool:
    """Scrolling, dwell time and model claims are not activities."""

    return real_activities >= 1


def apply_phase_suggestion(current: Phase, suggestion: str | None) -> Phase | None:
    """Return the *suggested* phase, never COMPLETED and never a direct write."""

    if suggestion is None:
        return None
    try:
        target = Phase(suggestion)
    except ValueError:
        return None
    if target is Phase.COMPLETED:
        return None  # only the student's explicit completion event may complete
    if target is current:
        return None
    return target
