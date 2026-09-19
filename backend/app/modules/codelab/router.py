from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.codelab.grading import grade_observations
from app.modules.codelab.models import CodeDraft, CodeRun, CodeTaskRevision
from app.modules.codelab.trusted import trusted_cases
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.learning.service import record_evidence
from app.modules.teaching.models import LessonSession

router = APIRouter()


class DraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_revision: int = Field(ge=1)
    code: str = Field(max_length=65_536)
    lesson_session_id: uuid.UUID | None = None


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_revision: int = Field(ge=1)
    code: str = Field(max_length=65_536)
    idempotency_key: str = Field(min_length=1, max_length=160)
    lesson_session_id: uuid.UUID | None = None


def _task_view(row: CodeTaskRevision) -> dict[str, Any]:
    return {
        "schema_version": "k12.code-task.v1",
        "task_id": row.task_id,
        "revision": row.revision,
        "status": row.status,
        "is_test_fixture": row.is_test_fixture,
        "review_status": row.review_status,
        "title": row.title,
        "description": row.description,
        "starter_code": row.starter_code,
        "entrypoint": row.entrypoint,
        "io_contract": row.io_contract,
        "examples": row.examples,
        "public_test_groups": row.test_manifest.get("public_groups", []),
        "chapter_binding": row.chapter_binding,
    }


def _run_view(row: CodeRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "task_revision": row.task_revision,
        "lesson_session_id": row.lesson_session_id,
        "status": row.status,
        "execution_status": row.execution_status,
        "correctness_status": row.correctness_status,
        "deterministic_score": row.deterministic_score,
        "code_hash": row.code_sha256,
        "code": row.code,
        "result": row.result,
        "feedback_status": row.feedback_status,
        "feedback": row.feedback,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
    }


async def _load_task(db: AsyncSession, task_id: str, revision: int) -> CodeTaskRevision:
    task = await db.scalar(
        select(CodeTaskRevision).where(
            CodeTaskRevision.task_id == task_id,
            CodeTaskRevision.revision == revision,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="编程任务版本不存在")
    return task


async def _runner_call(settings, payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.codelab_runner_url or not settings.codelab_runner_token:
        return {"error": "RUNNER_UNAVAILABLE"}

    def call() -> dict[str, Any]:
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

    return await asyncio.to_thread(call)


@router.get("/code-tasks")
async def list_code_tasks(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    rows = (
        await db.scalars(
            select(CodeTaskRevision)
            .where(CodeTaskRevision.status.in_(["DRAFT", "PUBLISHED"]))
            .order_by(CodeTaskRevision.task_id, CodeTaskRevision.revision)
        )
    ).all()
    return {"items": [_task_view(row) for row in rows]}


@router.get("/code-tasks/{task_id}")
async def get_code_task(
    task_id: str,
    revision: int | None = None,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    if revision is None:
        row = await db.scalar(
            select(CodeTaskRevision)
            .where(CodeTaskRevision.task_id == task_id)
            .order_by(CodeTaskRevision.revision.desc())
        )
    else:
        row = await _load_task(db, task_id, revision)
    if row is None or row.status not in {"DRAFT", "PUBLISHED"}:
        raise HTTPException(status_code=404, detail="编程任务不存在")
    return _task_view(row)


@router.get("/code-tasks/{task_id}/draft")
async def get_code_draft(
    task_id: str,
    revision: int,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await _load_task(db, task_id, revision)
    draft = await db.scalar(
        select(CodeDraft).where(
            CodeDraft.owner_user_id == context.user.id,
            CodeDraft.task_id == task_id,
            CodeDraft.task_revision == revision,
        )
    )
    return {
        "task_id": task_id,
        "task_revision": revision,
        "code": draft.code if draft else task.starter_code,
        "code_hash": draft.code_sha256
        if draft
        else hashlib.sha256(task.starter_code.encode()).hexdigest(),
        "updated_at": draft.updated_at if draft else None,
    }


@router.put("/code-tasks/{task_id}/draft", dependencies=[Depends(csrf_dependency)])
async def save_code_draft(
    task_id: str,
    payload: DraftPatch,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _load_task(db, task_id, payload.task_revision)
    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    draft = await db.scalar(
        select(CodeDraft).where(
            CodeDraft.owner_user_id == context.user.id,
            CodeDraft.task_id == task_id,
            CodeDraft.task_revision == payload.task_revision,
        )
    )
    if draft is None:
        draft = CodeDraft(
            owner_user_id=context.user.id,
            task_id=task_id,
            task_revision=payload.task_revision,
            lesson_session_id=payload.lesson_session_id,
            code=payload.code,
            code_sha256=code_hash,
        )
        db.add(draft)
    else:
        draft.code = payload.code
        draft.code_sha256 = code_hash
        draft.lesson_session_id = payload.lesson_session_id
    await db.commit()
    return {
        "task_id": task_id,
        "task_revision": payload.task_revision,
        "code": payload.code,
        "code_hash": code_hash,
        "updated_at": draft.updated_at,
    }


@router.post("/code-runs", dependencies=[Depends(csrf_dependency)])
async def create_code_run(
    payload: RunCreate,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task_id = request.query_params.get("task_id")
    if not task_id:
        raise HTTPException(status_code=422, detail="缺少 task_id")
    task = await _load_task(db, task_id, payload.task_revision)
    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    existing = await db.scalar(
        select(CodeRun).where(
            CodeRun.owner_user_id == context.user.id,
            CodeRun.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.task_id != task_id or existing.code_sha256 != code_hash:
            raise HTTPException(status_code=409, detail="幂等键已绑定其他代码快照")
        return {"run": _run_view(existing), "idempotent_replay": True}

    run = CodeRun(
        owner_user_id=context.user.id,
        task_id=task_id,
        task_revision=payload.task_revision,
        lesson_session_id=payload.lesson_session_id,
        idempotency_key=payload.idempotency_key,
        code=payload.code,
        code_sha256=code_hash,
        status="RUNNING",
        execution_status="RUNNING",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if not request.app.state.settings.codelab_runner_url:
        run.status = "UNAVAILABLE"
        run.execution_status = "UNAVAILABLE"
        run.result = {"error": "RUNNER_UNAVAILABLE"}
        run.completed_at = datetime.now(UTC)
        await db.commit()
        return {"run": _run_view(run), "idempotent_replay": False}

    observations: list[dict[str, Any]] = []
    runner_unavailable = False
    for case in trusted_cases(task_id):
        observation = await _runner_call(
            request.app.state.settings,
            {
                "case_id": case.case_id,
                "task_id": task_id,
                "task_revision": payload.task_revision,
                "entrypoint": task.entrypoint,
                "input": case.input,
                "student_code": payload.code,
                "owner_id": str(context.user.id),
                "lease_id": f"{run.id}-{case.case_id}",
            },
        )
        if observation.get("error") == "RUNNER_UNAVAILABLE":
            runner_unavailable = True
            break
        observations.append(observation)

    if runner_unavailable:
        run.status = "UNAVAILABLE"
        run.execution_status = "UNAVAILABLE"
        run.result = {"error": "RUNNER_UNAVAILABLE", "observations": observations}
    else:
        grade = grade_observations(task_id, payload.task_revision, observations)
        statuses = {item.get("execution_status") for item in observations}
        if "SYSTEM_ERROR" in statuses or grade.status == "SYSTEM_ERROR":
            execution = "SYSTEM_ERROR"
        elif "TIMEOUT" in statuses:
            execution = "TIMEOUT"
        elif "OUTPUT_LIMIT" in statuses:
            execution = "OUTPUT_LIMIT"
        elif "STUDENT_EXCEPTION" in statuses or "INVALID_JSON" in statuses:
            execution = "FAILED"
        else:
            execution = "SUCCEEDED"
        run.status = execution
        run.execution_status = execution
        run.correctness_status = grade.status if grade.status != "SYSTEM_ERROR" else "NOT_VERIFIED"
        run.deterministic_score = grade.deterministic_score
        run.result = {"grading": grade.as_dict(), "observations": observations}
        if payload.lesson_session_id and grade.status in {"PASSED", "PARTIAL", "FAILED"}:
            lesson = await db.scalar(
                select(LessonSession).where(
                    LessonSession.id == payload.lesson_session_id,
                    LessonSession.owner_user_id == context.user.id,
                )
            )
            if lesson is not None:
                await record_evidence(
                    db,
                    session=lesson,
                    kind="CODE_RUN_COMPLETED",
                    outcome="PASSED" if grade.status == "PASSED" else "FAILED",
                    reference=f"code-run:{run.id}:{code_hash}",
                )
    run.completed_at = datetime.now(UTC)
    await db.commit()
    return {"run": _run_view(run), "idempotent_replay": False}


@router.get("/code-runs/{run_id}")
async def get_code_run(
    run_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    run = await db.scalar(
        select(CodeRun).where(CodeRun.id == run_id, CodeRun.owner_user_id == context.user.id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return {"run": _run_view(run)}


@router.post("/code-runs/{run_id}/cancel", dependencies=[Depends(csrf_dependency)])
async def cancel_code_run(
    run_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    run = await db.scalar(
        select(CodeRun).where(CodeRun.id == run_id, CodeRun.owner_user_id == context.user.id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    if run.status in {"QUEUED", "RUNNING"}:
        run.status = "CANCELLED"
        run.execution_status = "CANCELLED"
        run.completed_at = datetime.now(UTC)
        await db.commit()
    return {"run": _run_view(run)}


@router.post("/code-runs/{run_id}/feedback", dependencies=[Depends(csrf_dependency)])
async def request_code_feedback(
    run_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    run = await db.scalar(
        select(CodeRun).where(CodeRun.id == run_id, CodeRun.owner_user_id == context.user.id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    if run.feedback_status == "READY":
        return {
            "run": _run_view(run),
            "fixture": request.app.state.settings.gateway_mode == "fixture",
        }
    if request.app.state.settings.gateway_mode != "fixture":
        run.feedback_status = "UNAVAILABLE"
        await db.commit()
        return {"run": _run_view(run), "fixture": False}
    run.feedback_status = "READY"
    run.feedback = {
        "status": "READY",
        "run_id": str(run.id),
        "code_hash": run.code_sha256,
        "summary": "这是本地合成反馈（非真实 Knodo）；确定性测试结果仍是唯一可信判定。",
        "references": [],
    }
    await db.commit()
    return {"run": _run_view(run), "fixture": True}
