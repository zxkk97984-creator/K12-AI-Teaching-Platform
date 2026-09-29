"""Lease based CodeRun consumer.

The API only persists a code snapshot. This worker is the sole place that
contacts the loopback runner, so examples and graded submissions share one
execution path while retaining different result projections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.assessment.models import QuizAttempt, QuizQuestion, QuizSession
from app.modules.codelab.grading import grade_observations
from app.modules.codelab.models import CodeRun, CodeTaskRevision
from app.modules.codelab.trusted import trusted_cases
from app.modules.learning.service import record_evidence
from app.modules.teaching.models import LessonSession

logger = logging.getLogger("k12.codelab.worker")


async def _complete_quiz_if_ready(db: AsyncSession, *, run: CodeRun) -> None:
    """Project a trusted CODE submission into the existing quiz state."""
    if run.purpose != "GRADE" or run.quiz_session_id is None or run.question_id is None:
        return
    session = await db.scalar(
        select(QuizSession).where(
            QuizSession.id == run.quiz_session_id,
            QuizSession.owner_user_id == run.owner_user_id,
        )
    )
    if session is None or session.status != "ACTIVE":
        return
    questions = list(
        await db.scalars(select(QuizQuestion).where(QuizQuestion.session_id == session.id))
    )
    answered = set(
        await db.scalars(
            select(QuizAttempt.question_id).where(
                QuizAttempt.session_id == session.id,
                QuizAttempt.attempt_no.is_not(None),
            )
        )
    )
    code_answered = set(
        await db.scalars(
            select(CodeRun.question_id).where(
                CodeRun.quiz_session_id == session.id,
                CodeRun.purpose == "GRADE",
                CodeRun.status.not_in(
                    ("QUEUED", "RUNNING", "CANCELLED", "UNAVAILABLE", "SYSTEM_ERROR")
                ),
                CodeRun.correctness_status.in_(("PASSED", "PARTIAL", "FAILED")),
            )
        )
    )
    complete = all(
        question.id in (code_answered if question.type == "CODE" else answered)
        for question in questions
    )
    if complete:
        session.status = "COMPLETED"
        session.completed_at = datetime.now(UTC)


def session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(settings.active_database_url, settings.app_env), expire_on_commit=False
    )


def _examples(task: CodeTaskRevision) -> list[dict]:
    rows: list[dict] = []
    for index, item in enumerate(task.examples or []):
        if not isinstance(item, dict) or not isinstance(item.get("input"), dict):
            continue
        rows.append({"case_id": f"example-{index + 1}", "input": item["input"]})
    return rows


def _request(settings: Settings, payload: dict) -> dict:
    if not settings.codelab_runner_url or not settings.codelab_runner_token:
        return {"error": "RUNNER_UNAVAILABLE"}
    request = urllib.request.Request(
        f"{settings.codelab_runner_url.rstrip('/')}/v1/run",
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.codelab_runner_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read(256 * 1024))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return {"error": "RUNNER_UNAVAILABLE"}


async def claim_code_run(db: AsyncSession, *, run_id: uuid.UUID, lease_seconds: int) -> str | None:
    run = await db.scalar(
        select(CodeRun).where(CodeRun.id == run_id).with_for_update(skip_locked=True)
    )
    if run is None or run.status != "QUEUED":
        return None
    token = uuid.uuid4().hex
    run.status = "RUNNING"
    run.execution_status = "RUNNING"
    run.lease_token = token
    run.started_at = datetime.now(UTC)
    run.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    await db.commit()
    return token


def _execution(observations: list[dict]) -> str:
    statuses = {item.get("execution_status") for item in observations}
    known = {
        "COMPLETED",
        "STUDENT_EXCEPTION",
        "INVALID_JSON",
        "TIMEOUT",
        "OUTPUT_LIMIT",
        "SYSTEM_ERROR",
    }
    if not observations or statuses - known or statuses & {"SYSTEM_ERROR", "RUNNER_ERROR"}:
        return "SYSTEM_ERROR"
    if "TIMEOUT" in statuses:
        return "TIMEOUT"
    if "OUTPUT_LIMIT" in statuses:
        return "OUTPUT_LIMIT"
    if "STUDENT_EXCEPTION" in statuses or "INVALID_JSON" in statuses:
        return "FAILED"
    return "SUCCEEDED"


def _safe_result(
    run: CodeRun, task: CodeTaskRevision, observations: list[dict], grading: dict | None
) -> dict:
    if run.purpose == "EXAMPLE":
        examples = task.examples if isinstance(task.examples, list) else []
        public_observations = []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            safe = {
                key: observation[key]
                for key in ("case_id", "execution_status", "actual_output", "stdout", "stderr")
                if key in observation
            }
            case_id = observation.get("case_id")
            if isinstance(case_id, str) and case_id.startswith("example-"):
                try:
                    index = int(case_id.removeprefix("example-")) - 1
                except ValueError:
                    index = -1
                if 0 <= index < len(examples) and isinstance(examples[index], dict):
                    safe["input"] = examples[index].get("input")
                    safe["expected_output"] = examples[index].get("output")
            public_observations.append(safe)
        return {
            "observations": public_observations,
        }
    if grading is None:
        raise ValueError("graded runs require deterministic grading data")
    group_by_case = {case.case_id: case.group_id for case in trusted_cases(task.task_id)}
    # Graded output intentionally excludes actual output, input, stdout and
    # stderr. Those fields may contain hidden test material or runner internals.
    return {
        "grading": grading,
        "observations": [
            {
                "case_id": item.get("case_id"),
                "group_id": group_by_case.get(item.get("case_id")),
                "execution_status": item.get("execution_status"),
            }
            for item in observations
        ],
    }


async def execute_code_run(settings: Settings, run_id: uuid.UUID) -> str:
    factory = session_factory(settings)
    async with factory() as db:
        token = await claim_code_run(
            db, run_id=run_id, lease_seconds=settings.teaching_lease_seconds
        )
        if token is None:
            return "NO_ATTEMPT"
        run = await db.scalar(select(CodeRun).where(CodeRun.id == run_id))
        task = await db.scalar(
            select(CodeTaskRevision).where(
                CodeTaskRevision.task_id == run.task_id,
                CodeTaskRevision.revision == run.task_revision,
            )
        )
        if task is None:
            run.status = "SYSTEM_ERROR"
            run.execution_status = "SYSTEM_ERROR"
            run.correctness_status = "NOT_VERIFIED"
            run.result = {"error": "TASK_REVISION_NOT_FOUND"}
            run.completed_at = datetime.now(UTC)
            run.lease_token = None
            await db.commit()
            return "FAILED"
        cases = (
            _examples(task)
            if run.purpose == "EXAMPLE"
            else [
                {"case_id": item.case_id, "input": item.input}
                for item in trusted_cases(run.task_id)
            ]
        )
        owner_id = str(run.owner_user_id)
        task_id = run.task_id
        task_revision = run.task_revision
        code = run.code
        lesson_id = run.lesson_session_id

    observations: list[dict] = []
    for case in cases:
        async with factory() as cancel_db:
            current_status = await cancel_db.scalar(
                select(CodeRun.status).where(CodeRun.id == run_id)
            )
        if current_status == "CANCELLED":
            return "CANCELLED"
        observation = await asyncio.to_thread(
            _request,
            settings,
            {
                "case_id": case["case_id"],
                "task_id": task_id,
                "task_revision": task_revision,
                "entrypoint": task.entrypoint,
                "input": case["input"],
                "student_code": code,
                "owner_id": owner_id,
                "lease_id": f"{run_id}-{case['case_id']}",
            },
        )
        if observation.get("error") == "RUNNER_UNAVAILABLE":
            observations = []
            break
        observations.append(observation)

    async with factory() as db:
        run = await db.scalar(select(CodeRun).where(CodeRun.id == run_id))
        task = await db.scalar(
            select(CodeTaskRevision).where(
                CodeTaskRevision.task_id == run.task_id,
                CodeTaskRevision.revision == run.task_revision,
            )
        )
        if run is None or task is None or run.lease_token != token:
            return "STALE"
        if run.status == "CANCELLED":
            return "CANCELLED"
        if not observations:
            run.status = "UNAVAILABLE"
            run.execution_status = "UNAVAILABLE"
            run.result = {"error": "RUNNER_UNAVAILABLE"}
        else:
            grade = (
                grade_observations(run.task_id, run.task_revision, observations)
                if run.purpose == "GRADE"
                else None
            )
            execution = _execution(observations)
            run.status = execution
            run.execution_status = execution
            if run.purpose == "EXAMPLE":
                run.correctness_status = "NOT_VERIFIED"
                run.deterministic_score = None
            else:
                assert grade is not None
                run.correctness_status = (
                    grade.status if grade.status != "SYSTEM_ERROR" else "NOT_VERIFIED"
                )
                run.deterministic_score = grade.deterministic_score
            run.result = _safe_result(run, task, observations, grade.as_dict() if grade else None)
            if (
                run.purpose == "GRADE"
                and lesson_id
                and grade is not None
                and grade.status in {"PASSED", "PARTIAL", "FAILED"}
            ):
                lesson = await db.scalar(
                    select(LessonSession).where(
                        LessonSession.id == lesson_id,
                        LessonSession.owner_user_id == run.owner_user_id,
                    )
                )
                if lesson is not None:
                    await record_evidence(
                        db,
                        session=lesson,
                        kind="CODE_RUN_COMPLETED",
                        outcome="PASSED" if grade.status == "PASSED" else "FAILED",
                        reference=f"code-run:{run.id}:{run.code_sha256}",
                    )
            await _complete_quiz_if_ready(db, run=run)
        run.completed_at = datetime.now(UTC)
        run.lease_token = None
        run.lease_expires_at = None
        await db.commit()
        return run.status


async def recover_code_runs(settings: Settings) -> int:
    factory = session_factory(settings)
    async with factory() as db:
        now = datetime.now(UTC)
        rows = list(
            await db.scalars(
                select(CodeRun).where(
                    CodeRun.status == "RUNNING",
                    CodeRun.lease_expires_at.is_not(None),
                    CodeRun.lease_expires_at < now,
                )
            )
        )
        for run in rows:
            run.status = "SYSTEM_ERROR"
            run.execution_status = "SYSTEM_ERROR"
            run.correctness_status = "NOT_VERIFIED"
            run.result = {"error": "CODELAB_WORKER_RESTARTED"}
            run.completed_at = now
            run.lease_token = None
        await db.commit()
        return len(rows)


__all__ = ["claim_code_run", "execute_code_run", "recover_code_runs", "session_factory"]
