"""T25 boundary between trusted CodeLab results and Tutor feedback.

The deterministic grading result is authoritative for correctness. Tutor
feedback is an optional, separately versioned opinion attached to the exact
run/code snapshot; it cannot add a score, change a status, or cite another
snapshot.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from runner.host.runner import ContainerResult, RunRequest

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.modules.codelab.grading import GradingResult


class FeedbackSnapshotError(ValueError):
    pass


class StaleFeedbackError(ValueError):
    pass


class FeedbackReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    line: int = Field(ge=1)
    kind: Literal["ERROR", "SUGGESTION", "STRENGTH"]
    message: str = Field(min_length=1, max_length=1200)


class TutorFeedback(BaseModel):
    """Local, non-authoritative feedback projection; no score field is allowed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["READY", "FAILED", "UNAVAILABLE"]
    run_id: str = Field(min_length=1, max_length=160)
    code_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(max_length=4000)
    references: list[FeedbackReference] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class CodeRunSnapshot:
    owner_id: str
    run_id: str
    task_id: str
    task_revision: int
    code_hash: str
    code_excerpt: str
    line_count: int
    execution_status: Literal["SUCCEEDED", "FAILED", "TIMEOUT", "OUTPUT_LIMIT", "SYSTEM_ERROR"]
    correctness_status: Literal["PASSED", "PARTIAL", "FAILED", "NOT_VERIFIED"]
    deterministic_score: float | None
    passed_cases: int | None
    total_cases: int | None
    stdout_excerpt: str
    error_excerpt: str

    def facts(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "code_hash": self.code_hash,
            "code_excerpt": self.code_excerpt,
            "execution_status": self.execution_status,
            "correctness_status": self.correctness_status,
            "stdout_excerpt": self.stdout_excerpt,
            "error_excerpt": self.error_excerpt,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
        }


def _excerpt(value: str, limit: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    return encoded[:limit].decode("utf-8", errors="replace")


def _execution_status(result: ContainerResult) -> str:
    return {
        "COMPLETED": "SUCCEEDED",
        "STUDENT_EXCEPTION": "FAILED",
        "INVALID_JSON": "FAILED",
        "TIMEOUT": "TIMEOUT",
        "OUTPUT_LIMIT": "OUTPUT_LIMIT",
        "RUNNER_ERROR": "SYSTEM_ERROR",
        "SYSTEM_ERROR": "SYSTEM_ERROR",
    }.get(result.execution_status, "SYSTEM_ERROR")


def _correctness_status(grade: GradingResult) -> str:
    if grade.status in {"PASSED", "PARTIAL", "FAILED", "NOT_VERIFIED"}:
        return grade.status
    return "NOT_VERIFIED"


def build_run_snapshot(
    *,
    owner_id: str,
    run_id: str,
    request: RunRequest,
    result: ContainerResult,
    grade: GradingResult,
) -> CodeRunSnapshot:
    """Bind runner output and trusted grading to one immutable code hash."""

    if request.owner_id != owner_id:
        raise FeedbackSnapshotError("run owner does not match the authenticated owner")
    if request.task_id != grade.task_id or request.task_revision != grade.task_revision:
        raise FeedbackSnapshotError("task revision differs between run and grading")
    if result.code_sha256 != request.code_sha256:
        raise FeedbackSnapshotError("runner result code hash differs from request")
    total_cases = sum(group.passed + group.failed + group.errors for group in grade.groups)
    passed_cases = sum(group.passed for group in grade.groups)
    code_excerpt = _excerpt(request.student_code, 12_000)
    return CodeRunSnapshot(
        owner_id=owner_id,
        run_id=run_id,
        task_id=request.task_id,
        task_revision=request.task_revision,
        code_hash=request.code_sha256,
        code_excerpt=code_excerpt,
        # Feedback line references must point into the exact excerpt sent to Tutor.
        line_count=code_excerpt.count("\n") + 1,
        execution_status=_execution_status(result),
        correctness_status=_correctness_status(grade),
        deterministic_score=grade.deterministic_score,
        passed_cases=passed_cases if grade.groups else None,
        total_cases=total_cases if grade.groups else None,
        stdout_excerpt=_excerpt(result.student_stdout, 3_000),
        error_excerpt=_excerpt(result.system_error or result.student_stderr, 3_000),
    )


def build_feedback_request(
    base_request: dict[str, Any],
    snapshot: CodeRunSnapshot,
    *,
    authenticated_owner_id: str,
) -> dict[str, Any]:
    """Attach only the current run facts to the frozen Tutor request semantic."""

    if authenticated_owner_id != snapshot.owner_id:
        raise FeedbackSnapshotError("feedback owner mismatch")
    if base_request.get("operation") != Operation.CODE_FEEDBACK.value:
        raise FeedbackSnapshotError("feedback request must use CODE_FEEDBACK")
    if snapshot.task_id not in base_request.get("allowed_code_task_ids", []):
        raise FeedbackSnapshotError("code task is not allowed in this Tutor request")
    payload = copy.deepcopy(base_request)
    payload["code_feedback_facts"] = snapshot.facts()
    problems = default_registry().validate_request(Operation.CODE_FEEDBACK, payload)
    if problems:
        raise FeedbackSnapshotError("CODE_FEEDBACK request failed the frozen schema")
    return payload


def feedback_idempotency_key(*, owner_id: str, run_id: str, code_hash: str) -> str:
    if not code_hash or len(code_hash) != 64:
        raise FeedbackSnapshotError("invalid code hash")
    value = f"{owner_id}:{run_id}:{code_hash}".encode()
    return hashlib.sha256(value).hexdigest()


def validate_feedback(raw: dict[str, Any], snapshot: CodeRunSnapshot) -> TutorFeedback:
    feedback = TutorFeedback.model_validate(raw)
    if feedback.run_id != snapshot.run_id or feedback.code_hash != snapshot.code_hash:
        raise StaleFeedbackError("Tutor feedback belongs to another run or code snapshot")
    for reference in feedback.references:
        if reference.line > snapshot.line_count:
            raise StaleFeedbackError("Tutor feedback references a line outside the code snapshot")
    return feedback


def public_code_run_projection(
    snapshot: CodeRunSnapshot, feedback: TutorFeedback | None = None
) -> dict[str, Any]:
    """Expose deterministic result and AI state separately; never merge scores."""

    if feedback is not None:
        validate_feedback(feedback.model_dump(mode="json"), snapshot)
    return {
        "run_id": snapshot.run_id,
        "task_id": snapshot.task_id,
        "task_revision": snapshot.task_revision,
        "code_hash": snapshot.code_hash,
        "execution_status": snapshot.execution_status,
        "correctness_status": snapshot.correctness_status,
        "deterministic_score": snapshot.deterministic_score,
        "passed_cases": snapshot.passed_cases,
        "total_cases": snapshot.total_cases,
        "ai_feedback_status": feedback.status if feedback is not None else "UNAVAILABLE",
        "ai_feedback": feedback.model_dump(mode="json") if feedback is not None else None,
    }
