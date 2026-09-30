from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.knodo import GatewayStatus
from app.integrations.knodo.operations import Operation
from app.modules.assessment.models import QuizQuestion, QuizSession
from app.modules.codelab.feedback import (
    FeedbackSnapshotError,
    TutorFeedback,
    build_feedback_request,
    build_run_snapshot,
    validate_feedback,
)
from app.modules.codelab.grading import GradingResult, GroupResult, grade_observations
from app.modules.codelab.models import (
    CodeDraft,
    CodeRun,
    CodeTaskCatalog,
    CodeTaskFavorite,
    CodeTaskRevision,
)
from app.modules.codelab.trusted import trusted_cases
from app.modules.content.models import Chapter, ChapterRevision, Course
from app.modules.content.service import viewer_scope_from_profile, visible_chapter_detail
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.learning.service import record_evidence
from app.modules.teaching.models import LessonSession

router = APIRouter()
_FEEDBACK_FACTS_VERSION = "persisted-grade-v1"


@router.get("/code-runner/status")
async def runner_status(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool | str]:
    await _task_stage(db, context.user.id)
    settings = request.app.state.settings
    if not settings.codelab_runner_url or not settings.codelab_runner_token:
        return {"available": False, "reason": "未启动真实 runner；代码可保存，暂不能运行"}

    def health() -> bool:
        try:
            with urllib.request.urlopen(
                f"{settings.codelab_runner_url.rstrip('/')}/health", timeout=2
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    available = await asyncio.to_thread(health)
    return {
        "available": available,
        "reason": "runner 已就绪" if available else "runner 暂时无法连接；代码可保存，暂不能运行",
    }


class DraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_revision: int = Field(ge=1)
    code: str = Field(max_length=65_536)
    lesson_session_id: uuid.UUID | None = None
    scope: dict[str, Any] | None = None
    base_revision: int = Field(default=0, ge=0)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_revision: int = Field(ge=1)
    code: str = Field(max_length=65_536)
    idempotency_key: str = Field(min_length=1, max_length=160)
    lesson_session_id: uuid.UUID | None = None
    purpose: str = Field(default="GRADE", pattern="^(EXAMPLE|GRADE)$")
    scope: dict[str, Any] | None = None
    quiz_session_id: uuid.UUID | None = None
    question_id: uuid.UUID | None = None
    async_run: bool = False


class CodeCatalogView(BaseModel):
    category: Literal["PYTHON_BASICS", "DATA_PROCESSING", "ALGORITHMS"] | None
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None
    tags: list[str]
    sort_order: int | None


class CodeProgressView(BaseModel):
    status: Literal["NOT_STARTED", "IN_PROGRESS", "PASSED"]
    has_draft: bool
    best_score: float | None
    latest_run_id: uuid.UUID | None
    latest_activity_at: datetime | None


class CourseLinkView(BaseModel):
    course_slug: str
    chapter_slug: str
    course_title: str
    chapter_title: str
    href: str | None
    available: bool


class CodeExampleView(BaseModel):
    input: dict[str, Any]
    output: Any


class CodePublicTestGroupView(BaseModel):
    id: str
    name: str
    dimension: Literal["F", "R"]
    max_score: int
    case_count: int


class CodeChapterBindingView(BaseModel):
    release_key: str | None = None
    course_slug: str
    chapter_slug: str
    revision: int
    stage: str
    knowledge_point_slugs: list[str]


class CodeTaskFacetsView(BaseModel):
    categories: list[str]
    difficulties: list[str]


class CodeTaskView(BaseModel):
    schema_version: str
    task_id: str
    revision: int
    status: str
    is_test_fixture: bool
    review_status: str
    title: str
    description: str
    starter_code: str
    entrypoint: str
    io_contract: dict[str, Any]
    examples: list[CodeExampleView]
    public_test_groups: list[CodePublicTestGroupView]
    chapter_binding: CodeChapterBindingView
    catalog: CodeCatalogView
    is_favorite: bool
    progress: CodeProgressView
    course_link: CourseLinkView | None


class CodeTaskPage(BaseModel):
    items: list[CodeTaskView]
    total: int
    limit: int
    offset: int
    facets: CodeTaskFacetsView


class FavoriteView(BaseModel):
    task_id: str
    is_favorite: bool


class CodeRunView(BaseModel):
    id: uuid.UUID
    task_id: str
    task_revision: int
    lesson_session_id: uuid.UUID | None
    scope_key: str
    purpose: str
    quiz_session_id: uuid.UUID | None
    question_id: uuid.UUID | None
    status: str
    execution_status: str
    correctness_status: str
    deterministic_score: float | None
    code_hash: str
    code: str
    result: dict[str, Any] | None
    feedback_status: str
    feedback: dict[str, Any] | None
    feedback_eligible: bool
    feedback_unavailable_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class CodeRunSummaryView(BaseModel):
    id: uuid.UUID
    task_id: str
    task_revision: int
    title: str
    purpose: str
    status: str
    execution_status: str
    correctness_status: str
    deterministic_score: float | None
    score_scale: int
    feedback_status: str
    feedback_source: str | None
    scope_kind: str
    source_label: str
    created_at: datetime
    completed_at: datetime | None


class CodeRunPage(BaseModel):
    items: list[CodeRunSummaryView]
    total: int
    limit: int
    offset: int


class CodeTaskSnapshotView(BaseModel):
    task_id: str
    revision: int
    title: str
    description: str
    entrypoint: str
    examples: list[CodeExampleView]
    chapter_binding: CodeChapterBindingView


class CodeRunSourceView(BaseModel):
    scope_kind: str
    label: str
    href: str | None


class CodeRunDetailView(BaseModel):
    run: CodeRunView
    task_snapshot: CodeTaskSnapshotView
    source: CodeRunSourceView


class CodeRunCreateView(BaseModel):
    run: CodeRunView
    idempotent_replay: bool


class CodeFeedbackView(BaseModel):
    run: CodeRunView
    fixture: bool
    reason: str | None = None


def _request_hash(*, task_id: str, payload: RunCreate, scope_key: str) -> str:
    canonical = json.dumps(
        {
            "task_id": task_id,
            "task_revision": payload.task_revision,
            "code": payload.code,
            "scope_key": scope_key,
            "purpose": payload.purpose,
            "quiz_session_id": str(payload.quiz_session_id) if payload.quiz_session_id else None,
            "question_id": str(payload.question_id) if payload.question_id else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _resolve_scope(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    scope: dict[str, Any] | None,
    settings: Any | None = None,
    lesson_session_id: uuid.UUID | None = None,
    quiz_session_id: uuid.UUID | None = None,
    question_id: uuid.UUID | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate and normalize a workspace scope against server-owned rows."""

    if scope is None:
        if lesson_session_id is None:
            if quiz_session_id is not None or question_id is not None:
                raise HTTPException(status_code=422, detail="standalone 作用域不能带题目引用")
            return "standalone", {"kind": "STANDALONE"}
        scope = {"kind": "LESSON", "lesson_session_id": str(lesson_session_id)}
    if not isinstance(scope, dict):
        raise HTTPException(status_code=422, detail="作用域格式无效")
    kind = str(scope.get("kind") or "").upper()
    allowed = {
        "STANDALONE": {"kind"},
        "CHAPTER": {"kind", "chapter_revision_id"},
        "LESSON": {"kind", "lesson_session_id"},
        "QUIZ": {"kind", "quiz_session_id", "question_id"},
    }
    if kind not in allowed or set(scope) != allowed[kind]:
        raise HTTPException(status_code=422, detail="未知或不完整的编程作用域")
    if kind == "STANDALONE":
        if lesson_session_id or quiz_session_id or question_id:
            raise HTTPException(status_code=422, detail="standalone 作用域不能带业务引用")
        return "standalone", {"kind": "STANDALONE"}
    try:
        if kind == "CHAPTER":
            revision_id = uuid.UUID(str(scope["chapter_revision_id"]))
            row = await db.scalar(select(ChapterRevision).where(ChapterRevision.id == revision_id))
            if row is None:
                raise HTTPException(status_code=422, detail="章节版本不存在")
            if settings is not None:
                profile = await db.scalar(
                    select(LearnerProfile).where(LearnerProfile.user_id == owner_id)
                )
                if profile is None or not await visible_chapter_detail(
                    db,
                    chapter_id=row.chapter_id,
                    revision=row.revision,
                    viewer=viewer_scope_from_profile(profile, settings),
                ):
                    raise HTTPException(status_code=404, detail="章节版本不可用")
            return f"chapter:{revision_id}", {
                "kind": "CHAPTER",
                "chapter_revision_id": str(revision_id),
            }
        if kind == "LESSON":
            lesson_id = uuid.UUID(str(scope["lesson_session_id"]))
            if lesson_session_id is not None and lesson_id != lesson_session_id:
                raise HTTPException(status_code=422, detail="教学会话引用不一致")
            lesson = await db.scalar(
                select(LessonSession).where(
                    LessonSession.id == lesson_id, LessonSession.owner_user_id == owner_id
                )
            )
            if lesson is None:
                raise HTTPException(status_code=404, detail="教学会话不存在")
            return f"lesson:{lesson_id}", {"kind": "LESSON", "lesson_session_id": str(lesson_id)}
        quiz_id = uuid.UUID(str(scope["quiz_session_id"]))
        question_uuid = uuid.UUID(str(scope["question_id"]))
        if quiz_session_id is not None and quiz_id != quiz_session_id:
            raise HTTPException(status_code=422, detail="练习会话引用不一致")
        if question_id is not None and question_uuid != question_id:
            raise HTTPException(status_code=422, detail="题目引用不一致")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="作用域 ID 无效") from exc
    quiz = await db.scalar(
        select(QuizSession).where(QuizSession.id == quiz_id, QuizSession.owner_user_id == owner_id)
    )
    question = await db.scalar(
        select(QuizQuestion).where(
            QuizQuestion.id == question_uuid, QuizQuestion.session_id == quiz_id
        )
    )
    if quiz is None or question is None:
        raise HTTPException(status_code=404, detail="练习题目不存在")
    return f"quiz:{quiz_id}:{question_uuid}", {
        "kind": "QUIZ",
        "quiz_session_id": str(quiz_id),
        "question_id": str(question_uuid),
    }


def _task_view(
    row: CodeTaskRevision,
    *,
    catalog: CodeTaskCatalog | None = None,
    is_favorite: bool = False,
    progress: dict[str, Any] | None = None,
    course_link: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "catalog": {
            "category": catalog.category if catalog else None,
            "difficulty": catalog.difficulty if catalog else None,
            "tags": catalog.tags if catalog else [],
            "sort_order": catalog.sort_order if catalog else None,
        },
        "is_favorite": is_favorite,
        "progress": progress
        or {
            "status": "NOT_STARTED",
            "has_draft": False,
            "best_score": None,
            "latest_run_id": None,
            "latest_activity_at": None,
        },
        "course_link": course_link,
    }


def _feedback_eligibility(row: CodeRun, settings: Any | None = None) -> tuple[bool, str | None]:
    if row.purpose != "GRADE":
        return False, "EXAMPLE_HAS_NO_GRADE"
    if row.status in {"QUEUED", "RUNNING"}:
        return False, "RUN_NOT_COMPLETE"
    if row.execution_status in {"UNAVAILABLE", "CANCELLED", "SYSTEM_ERROR"}:
        return False, "TRUSTED_RESULT_UNAVAILABLE"
    if row.execution_status != "SUCCEEDED":
        return False, "TRUSTED_RESULT_UNAVAILABLE"
    if row.status != "SUCCEEDED" or row.correctness_status not in {"PASSED", "PARTIAL", "FAILED"}:
        return False, "TRUSTED_RESULT_UNAVAILABLE"
    if row.deterministic_score is None or not isinstance(row.result, dict):
        return False, "TRUSTED_RESULT_UNAVAILABLE"
    grading = row.result.get("grading")
    if (
        not isinstance(grading, dict)
        or grading.get("schema_version") != "k12.grading-result.v1"
        or grading.get("task_id") != row.task_id
        or grading.get("task_revision") != row.task_revision
        or grading.get("status") != row.correctness_status
        or grading.get("deterministic_score") != row.deterministic_score
        or not isinstance(grading.get("groups"), list)
    ):
        return False, "TRUSTED_RESULT_UNAVAILABLE"
    if settings is not None and settings.gateway_mode not in {"fixture", "knodo"}:
        return False, "AI_DISABLED"
    return True, None


def _run_view(
    row: CodeRun,
    settings: Any | None = None,
    task: CodeTaskRevision | None = None,
) -> dict[str, Any]:
    feedback_eligible, feedback_reason = _feedback_eligibility(row, settings)
    stale_feedback = (
        row.purpose == "GRADE"
        and row.feedback_status == "READY"
        and (row.feedback or {}).get("facts_version") != _FEEDBACK_FACTS_VERSION
    )
    feedback_evidence_valid, _ = _feedback_eligibility(row)
    public_feedback = (
        {
            "status": "STALE",
            "summary": "旧代码反馈使用了不完整的判分快照，请重新请求。",
            "references": [],
        }
        if stale_feedback
        else row.feedback
        if feedback_evidence_valid
        else None
    )
    return {
        "id": row.id,
        "task_id": row.task_id,
        "task_revision": row.task_revision,
        "lesson_session_id": row.lesson_session_id,
        "scope_key": row.scope_key,
        "purpose": row.purpose,
        "quiz_session_id": row.quiz_session_id,
        "question_id": row.question_id,
        "status": row.status,
        "execution_status": row.execution_status,
        "correctness_status": row.correctness_status,
        "deterministic_score": row.deterministic_score,
        "code_hash": row.code_sha256,
        "code": row.code,
        "result": _public_result(row, task),
        "feedback_status": (
            "STALE"
            if stale_feedback
            else row.feedback_status
            if feedback_evidence_valid
            else "UNAVAILABLE"
        ),
        "feedback": public_feedback,
        "feedback_eligible": feedback_eligible,
        "feedback_unavailable_reason": feedback_reason,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
    }


def _public_result(row: CodeRun, task: CodeTaskRevision | None = None) -> dict[str, Any] | None:
    if not isinstance(row.result, dict):
        return row.result
    if row.purpose == "EXAMPLE":
        observations = row.result.get("observations")
        if not isinstance(observations, list):
            return {"error": row.result.get("error")}
        examples = task.examples if task is not None and isinstance(task.examples, list) else []
        public_observations = []
        for item in observations:
            if not isinstance(item, dict):
                continue
            safe = {
                key: item[key]
                for key in ("case_id", "execution_status", "actual_output", "stdout", "stderr")
                if key in item
            }
            case_id = item.get("case_id")
            if isinstance(case_id, str) and case_id.startswith("example-"):
                try:
                    example_index = int(case_id.removeprefix("example-")) - 1
                except ValueError:
                    example_index = -1
                if 0 <= example_index < len(examples):
                    example = examples[example_index]
                    if isinstance(example, dict):
                        safe["input"] = example.get("input")
                        safe["expected_output"] = example.get("output")
            public_observations.append(safe)
        return {"observations": public_observations}
    grading = row.result.get("grading")
    observations = row.result.get("observations")
    if not isinstance(observations, list):
        return {"grading": grading} if grading is not None else {"error": row.result.get("error")}
    return {
        "grading": grading,
        "observations": [
            {
                key: item.get(key)
                for key in ("case_id", "group_id", "execution_status")
                if isinstance(item, dict) and key in item
            }
            for item in observations
        ],
    }


def _code_feedback_request(*, run: CodeRun, task: CodeTaskRevision) -> dict[str, Any]:
    """Build the frozen semantic request for one persisted CodeLab run.

    Code feedback has no lesson session of its own.  The task revision is the
    source of the chapter and learner stage, while the run facts are attached
    by ``build_feedback_request`` after the deterministic result is rebuilt.
    Keeping this request local means student supplied task/chapter fields can
    never widen the Knodo action or source allow-lists.
    """

    binding = task.chapter_binding if isinstance(task.chapter_binding, dict) else {}
    stage = binding.get("stage")
    if stage not in {"PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"}:
        raise ValueError("编程任务缺少有效学段绑定")
    objectives = [
        value
        for value in binding.get("knowledge_point_slugs", [])
        if isinstance(value, str) and value
    ][:12]
    if not objectives:
        objectives = [f"{task.task_id}-code"]
    chapter_slug = str(binding.get("chapter_slug") or task.task_id)[:160]
    curriculum_revision = f"codelab:{task.task_id}:{task.revision}"[:160]
    return {
        "schema_version": "k12.teaching.request.v1",
        "request_id": f"codelab-feedback-{run.id}",
        "lesson_session_id": f"codelab-{run.id}",
        "base_revision": 0,
        "curriculum_revision": curriculum_revision,
        "policy_revision": "codelab-feedback-v1",
        "operation": Operation.CODE_FEEDBACK.value,
        "event": "CODE_RUN_COMPLETED",
        "current_phase": "PRACTICE",
        "learner": {"stage": stage, "grade": None, "preferred_style": "CODE"},
        "chapter": {
            "id": chapter_slug,
            "title": task.title[:250],
            "objective_ids": objectives,
        },
        "knowledge_context": [
            {
                "source_id": f"codelab-task:{task.task_id}",
                "revision": str(task.revision),
                "locator": "task.description",
                "text": task.description[:8000] or "编程任务代码反馈",
            }
        ],
        "evidence": [],
        "allowed_actions": [],
        "allowed_resource_ids": [],
        "allowed_animation_ids": [],
        "allowed_code_task_ids": [task.task_id],
        "allowed_phase_suggestions": ["PRACTICE", "REFLECT"],
        "limits": {
            "max_quiz_questions": 0,
            "allowed_difficulties": ["EASY"],
            "max_reply_chars": 1200,
        },
        "student_input": (
            "请根据这次代码运行的确定性测试结果，给出适合学生理解的调试建议。"
            "确定性判分结果是唯一可信判定，不要声称修改分数或测试结论。"
        ),
        "code_feedback_facts": None,
    }


def _code_feedback_validation_context(request: dict[str, Any]) -> dict[str, Any]:
    """Allow only source ids actually included in the trusted task snapshot."""
    return {
        **request,
        "allowed_source_ids": [
            item["source_id"]
            for item in request.get("knowledge_context", [])
            if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        ],
        "allowed_evidence_ids": [],
    }


def _snapshot_for_run(*, run: CodeRun, task: CodeTaskRevision, owner_id: str):
    """Use the saved trusted grade; graded observations omit hidden outputs."""

    result_payload = run.result if isinstance(run.result, dict) else {}
    observations = result_payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise FeedbackSnapshotError("deterministic runner observations are unavailable")
    if run.purpose != "GRADE":
        raise FeedbackSnapshotError("AI feedback requires a graded submission")
    saved = result_payload.get("grading")
    if (
        not isinstance(saved, dict)
        or saved.get("schema_version") != "k12.grading-result.v1"
        or saved.get("task_id") != task.task_id
        or saved.get("task_revision") != task.revision
        or saved.get("status") not in {"PASSED", "PARTIAL", "FAILED"}
        or saved.get("status") != run.correctness_status
        or saved.get("deterministic_score") != run.deterministic_score
        or not isinstance(run.deterministic_score, (int, float))
        or isinstance(run.deterministic_score, bool)
        or not isinstance(saved.get("groups"), list)
    ):
        raise FeedbackSnapshotError("persisted grade does not match this run")
    try:
        groups = tuple(
            GroupResult(
                group_id=item["id"],
                dimension=item["dimension"],
                max_score=float(item["max_score"]),
                passed=int(item["passed"]),
                failed=int(item["failed"]),
                errors=int(item["errors"]),
                score=float(item["score"]) if item["score"] is not None else None,
            )
            for item in saved["groups"]
        )
    except (KeyError, TypeError, ValueError) as caught:
        raise FeedbackSnapshotError("persisted grade groups are invalid") from caught
    if any(
        group.dimension not in {"F", "R"} or min(group.passed, group.failed, group.errors) < 0
        for group in groups
    ):
        raise FeedbackSnapshotError("persisted grade groups are invalid")
    grade = GradingResult(
        task_id=task.task_id,
        task_revision=task.revision,
        status=saved["status"],
        deterministic_tests_available=True,
        deterministic_score=float(run.deterministic_score),
        groups=groups,
    )
    first_case = trusted_cases(task.task_id)[0]
    from runner.host.runner import ContainerResult, RunRequest

    request = RunRequest.from_payload(
        {
            "case_id": first_case.case_id,
            "task_id": task.task_id,
            "task_revision": task.revision,
            "entrypoint": task.entrypoint,
            "input": first_case.input,
            "student_code": run.code,
            "owner_id": owner_id,
            "lease_id": str(run.id),
        }
    )
    # The persisted aggregate status is authoritative for the run as a whole.
    execution_status = {
        "SUCCEEDED": "COMPLETED",
        "FAILED": "STUDENT_EXCEPTION",
        "TIMEOUT": "TIMEOUT",
        "OUTPUT_LIMIT": "OUTPUT_LIMIT",
        "SYSTEM_ERROR": "RUNNER_ERROR",
    }.get(run.execution_status, "RUNNER_ERROR")
    stdout = "\n".join(
        str(item.get("stdout", ""))[:1000]
        for item in observations
        if isinstance(item, dict) and item.get("stdout")
    )[:3000]
    stderr = "\n".join(
        str(item.get("stderr", ""))[:1000]
        for item in observations
        if isinstance(item, dict) and item.get("stderr")
    )[:3000]
    result = ContainerResult(
        case_id=first_case.case_id,
        execution_status=execution_status,
        student_stdout=stdout,
        student_stderr=stderr,
        code_sha256=run.code_sha256,
        system_error=("runner/system failure" if execution_status == "RUNNER_ERROR" else None),
    )
    return build_run_snapshot(
        owner_id=owner_id,
        run_id=str(run.id),
        request=request,
        result=result,
        grade=grade,
    )


async def _task_stage(db: AsyncSession, owner_id: uuid.UUID) -> str:
    profile = await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == owner_id))
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="请先选择学段")
    return profile.stage


def _matches_stage(task: CodeTaskRevision, stage: str) -> bool:
    binding = task.chapter_binding if isinstance(task.chapter_binding, dict) else {}
    return binding.get("stage") == stage


async def _load_task(
    db: AsyncSession,
    task_id: str,
    revision: int,
    owner_id: uuid.UUID | None = None,
) -> CodeTaskRevision:
    task = await db.scalar(
        select(CodeTaskRevision).where(
            CodeTaskRevision.task_id == task_id,
            CodeTaskRevision.revision == revision,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="编程任务版本不存在")
    if owner_id is not None and not _matches_stage(task, await _task_stage(db, owner_id)):
        raise HTTPException(status_code=404, detail="当前学段没有这项编程任务")
    return task


async def _course_links_for_tasks(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    settings: Any,
    tasks: list[CodeTaskRevision],
) -> dict[tuple[str, str, int], dict[str, Any] | None]:
    bindings = {
        (
            str(row.chapter_binding.get("course_slug", "")),
            str(row.chapter_binding.get("chapter_slug", "")),
            int(row.chapter_binding.get("revision", row.revision)),
        )
        for row in tasks
        if isinstance(row.chapter_binding, dict)
    }
    if not bindings:
        return {}
    profile = await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == owner_id))
    rows = (
        await db.execute(
            select(Chapter, Course)
            .join(Course, Course.id == Chapter.course_id)
            .where(
                tuple_(Course.stable_slug, Chapter.stable_slug).in_(
                    {(course_slug, chapter_slug) for course_slug, chapter_slug, _ in bindings}
                )
            )
        )
    ).all()
    by_slug = {
        (course.stable_slug, chapter.stable_slug): (chapter, course) for chapter, course in rows
    }
    viewer = viewer_scope_from_profile(profile, settings)
    result: dict[tuple[str, str, int], dict[str, Any] | None] = {}
    for course_slug, chapter_slug, revision in bindings:
        pair = by_slug.get((course_slug, chapter_slug))
        if pair is None:
            result[(course_slug, chapter_slug, revision)] = None
            continue
        chapter, course = pair
        detail = await visible_chapter_detail(
            db,
            chapter_id=chapter.id,
            revision=revision,
            viewer=viewer,
        )
        result[(course_slug, chapter_slug, revision)] = {
            "course_slug": course_slug,
            "chapter_slug": chapter_slug,
            "course_title": course.title,
            "chapter_title": chapter.title,
            "href": f"/chapters/{chapter.id}?revision={revision}" if detail is not None else None,
            "available": detail is not None,
        }
    return result


async def _project_tasks(
    db: AsyncSession,
    *,
    request: Request,
    owner_id: uuid.UUID,
    tasks: list[CodeTaskRevision],
) -> list[dict[str, Any]]:
    if not tasks:
        return []
    ids = {row.task_id for row in tasks}
    revision_by_id = {row.task_id: row.revision for row in tasks}
    keys = [(row.task_id, row.revision) for row in tasks]
    catalog_rows = (
        await db.scalars(
            select(CodeTaskCatalog).where(
                tuple_(CodeTaskCatalog.task_id, CodeTaskCatalog.task_revision).in_(keys)
            )
        )
    ).all()
    catalogs = {(row.task_id, row.task_revision): row for row in catalog_rows}
    favorites = set(
        await db.scalars(
            select(CodeTaskFavorite.task_id).where(
                CodeTaskFavorite.owner_user_id == owner_id,
                CodeTaskFavorite.task_id.in_(ids),
            )
        )
    )
    drafts = (
        await db.scalars(
            select(CodeDraft).where(
                CodeDraft.owner_user_id == owner_id,
                CodeDraft.task_id.in_(ids),
            )
        )
    ).all()
    runs = (
        await db.scalars(
            select(CodeRun).where(
                CodeRun.owner_user_id == owner_id,
                CodeRun.task_id.in_(ids),
            )
        )
    ).all()
    draft_by_task: dict[str, list[CodeDraft]] = {}
    for row in drafts:
        if revision_by_id.get(row.task_id) == row.task_revision:
            draft_by_task.setdefault(row.task_id, []).append(row)
    run_by_task: dict[str, list[CodeRun]] = {}
    for row in runs:
        if revision_by_id.get(row.task_id) == row.task_revision:
            run_by_task.setdefault(row.task_id, []).append(row)
    course_links = await _course_links_for_tasks(
        db,
        owner_id=owner_id,
        settings=request.app.state.settings,
        tasks=tasks,
    )
    projected: list[dict[str, Any]] = []
    for task in tasks:
        task_drafts = draft_by_task.get(task.task_id, [])
        task_runs = sorted(
            run_by_task.get(task.task_id, []),
            key=lambda run: (run.created_at, str(run.id)),
            reverse=True,
        )
        valid_grade_runs = [
            run
            for run in task_runs
            if run.purpose == "GRADE"
            and run.status == "SUCCEEDED"
            and run.correctness_status in {"PASSED", "PARTIAL", "FAILED"}
            and run.deterministic_score is not None
        ]
        passed = any(run.correctness_status == "PASSED" for run in valid_grade_runs)
        has_started = bool(task_drafts or task_runs)
        activity = [row.updated_at for row in task_drafts if row.updated_at is not None]
        activity.extend(row.created_at for row in task_runs if row.created_at is not None)
        binding = task.chapter_binding if isinstance(task.chapter_binding, dict) else {}
        key = (
            str(binding.get("course_slug", "")),
            str(binding.get("chapter_slug", "")),
            int(binding.get("revision", task.revision)),
        )
        catalog = catalogs.get((task.task_id, task.revision))
        projected.append(
            _task_view(
                task,
                catalog=catalog,
                is_favorite=task.task_id in favorites,
                progress={
                    "status": "PASSED"
                    if passed
                    else "IN_PROGRESS"
                    if has_started
                    else "NOT_STARTED",
                    "has_draft": bool(task_drafts),
                    "best_score": max(
                        (run.deterministic_score for run in valid_grade_runs), default=None
                    ),
                    "latest_run_id": task_runs[0].id if task_runs else None,
                    "latest_activity_at": max(activity, default=None),
                },
                course_link=course_links.get(key),
            )
        )
    return projected


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


@router.get("/code-tasks", response_model=CodeTaskPage)
async def list_code_tasks(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    category: Literal["PYTHON_BASICS", "DATA_PROCESSING", "ALGORITHMS"] | None = None,
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None,
    progress: Literal["NOT_STARTED", "IN_PROGRESS", "PASSED"] | None = None,
    favorite_only: bool = False,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stage = await _task_stage(db, context.user.id)
    rows = (
        await db.scalars(
            select(CodeTaskRevision)
            .where(CodeTaskRevision.status.in_(["DRAFT", "PUBLISHED"]))
            .order_by(CodeTaskRevision.task_id, CodeTaskRevision.revision.desc())
        )
    ).all()
    latest: dict[str, CodeTaskRevision] = {}
    for row in rows:
        if _matches_stage(row, stage):
            latest.setdefault(row.task_id, row)
    projected = await _project_tasks(
        db,
        request=request,
        owner_id=context.user.id,
        tasks=list(latest.values()),
    )
    category_facets = sorted(
        {item["catalog"]["category"] for item in projected if item["catalog"]["category"]}
    )
    difficulty_facets = sorted(
        {item["catalog"]["difficulty"] for item in projected if item["catalog"]["difficulty"]}
    )
    query = (q or "").strip().casefold()
    filtered = []
    for item in projected:
        catalog = item["catalog"]
        if category and catalog["category"] != category:
            continue
        if difficulty and catalog["difficulty"] != difficulty:
            continue
        if progress and item["progress"]["status"] != progress:
            continue
        if favorite_only and not item["is_favorite"]:
            continue
        searchable = " ".join(
            [
                item["title"],
                item["task_id"],
                *catalog["tags"],
                *item["chapter_binding"].get("knowledge_point_slugs", []),
            ]
        ).casefold()
        if query and query not in searchable:
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda item: (
            item["catalog"]["sort_order"] is None,
            item["catalog"]["sort_order"] if item["catalog"]["sort_order"] is not None else 0,
            item["task_id"],
        )
    )
    total = len(filtered)
    return {
        "items": filtered[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": {"categories": category_facets, "difficulties": difficulty_facets},
    }


@router.get("/code-tasks/{task_id}", response_model=CodeTaskView)
async def get_code_task(
    task_id: str,
    request: Request,
    revision: int | None = None,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if revision is None:
        row = await db.scalar(
            select(CodeTaskRevision)
            .where(
                CodeTaskRevision.task_id == task_id,
                CodeTaskRevision.status.in_(["DRAFT", "PUBLISHED"]),
            )
            .order_by(CodeTaskRevision.revision.desc())
        )
    else:
        row = await _load_task(db, task_id, revision, context.user.id)
    if (
        row is None
        or row.status not in {"DRAFT", "PUBLISHED"}
        or not _matches_stage(row, await _task_stage(db, context.user.id))
    ):
        raise HTTPException(status_code=404, detail="编程任务不存在")
    projected = await _project_tasks(db, request=request, owner_id=context.user.id, tasks=[row])
    return projected[0]


@router.put(
    "/code-tasks/{task_id}/favorite",
    response_model=FavoriteView,
    dependencies=[Depends(csrf_dependency)],
)
async def favorite_code_task(
    task_id: str,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await db.scalar(
        select(CodeTaskRevision)
        .where(
            CodeTaskRevision.task_id == task_id,
            CodeTaskRevision.status.in_(["DRAFT", "PUBLISHED"]),
        )
        .order_by(CodeTaskRevision.revision.desc())
    )
    if row is None or not _matches_stage(row, await _task_stage(db, context.user.id)):
        raise HTTPException(status_code=404, detail="当前学段没有这项编程任务")
    statement = pg_insert(CodeTaskFavorite).values(
        owner_user_id=context.user.id,
        task_id=task_id,
    )
    await db.execute(
        statement.on_conflict_do_nothing(
            index_elements=[CodeTaskFavorite.owner_user_id, CodeTaskFavorite.task_id]
        )
    )
    await db.commit()
    return {"task_id": task_id, "is_favorite": True}


@router.delete(
    "/code-tasks/{task_id}/favorite",
    response_model=FavoriteView,
    dependencies=[Depends(csrf_dependency)],
)
async def unfavorite_code_task(
    task_id: str,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stage = await _task_stage(db, context.user.id)
    known = await db.scalar(
        select(CodeTaskRevision.id).where(CodeTaskRevision.task_id == task_id).limit(1)
    )
    if known is None:
        raise HTTPException(status_code=404, detail="编程任务不存在")
    stage_rows = (
        await db.scalars(select(CodeTaskRevision).where(CodeTaskRevision.task_id == task_id))
    ).all()
    if not any(_matches_stage(row, stage) for row in stage_rows):
        raise HTTPException(status_code=404, detail="当前学段没有这项编程任务")
    await db.execute(
        delete(CodeTaskFavorite).where(
            CodeTaskFavorite.owner_user_id == context.user.id,
            CodeTaskFavorite.task_id == task_id,
        )
    )
    await db.commit()
    return {"task_id": task_id, "is_favorite": False}


@router.get("/code-tasks/{task_id}/draft")
async def get_code_draft(
    task_id: str,
    revision: int,
    request: Request,
    scope_kind: str | None = None,
    scope_id: str | None = None,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await _load_task(db, task_id, revision, context.user.id)
    if not scope_kind and not scope_id:
        scope_key = "standalone"
    else:
        kind = (scope_kind or "").upper()
        if kind == "STANDALONE" and not scope_id:
            scope_key = "standalone"
        elif kind == "CHAPTER" and scope_id:
            scope_key, _ = await _resolve_scope(
                db,
                owner_id=context.user.id,
                scope={"kind": "CHAPTER", "chapter_revision_id": scope_id},
                settings=request.app.state.settings,
            )
        elif kind == "LESSON" and scope_id:
            scope_key, _ = await _resolve_scope(
                db,
                owner_id=context.user.id,
                scope={"kind": "LESSON", "lesson_session_id": scope_id},
            )
        elif kind == "QUIZ" and scope_id and ":" in scope_id:
            quiz_id, question_id = scope_id.split(":", 1)
            scope_key, _ = await _resolve_scope(
                db,
                owner_id=context.user.id,
                scope={
                    "kind": "QUIZ",
                    "quiz_session_id": quiz_id,
                    "question_id": question_id,
                },
            )
        else:
            raise HTTPException(status_code=422, detail="未知或不完整的编程作用域")
    draft = await db.scalar(
        select(CodeDraft).where(
            CodeDraft.owner_user_id == context.user.id,
            CodeDraft.task_id == task_id,
            CodeDraft.task_revision == revision,
            CodeDraft.scope_key == scope_key,
        )
    )
    return {
        "task_id": task_id,
        "task_revision": revision,
        "scope_key": scope_key,
        "revision_number": draft.revision if draft else 0,
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
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _load_task(db, task_id, payload.task_revision, context.user.id)
    scope_key, _normalized_scope = await _resolve_scope(
        db,
        owner_id=context.user.id,
        scope=payload.scope,
        lesson_session_id=payload.lesson_session_id,
        settings=request.app.state.settings,
    )
    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    draft = await db.scalar(
        select(CodeDraft)
        .where(
            CodeDraft.owner_user_id == context.user.id,
            CodeDraft.task_id == task_id,
            CodeDraft.task_revision == payload.task_revision,
            CodeDraft.scope_key == scope_key,
        )
        .with_for_update()
    )
    if draft is None:
        if payload.base_revision != 0:
            raise HTTPException(status_code=409, detail="草稿版本已变化，请重新读取")
        draft = CodeDraft(
            owner_user_id=context.user.id,
            task_id=task_id,
            task_revision=payload.task_revision,
            lesson_session_id=payload.lesson_session_id,
            scope_key=scope_key,
            code=payload.code,
            code_sha256=code_hash,
        )
        db.add(draft)
    else:
        if payload.base_revision != draft.revision:
            raise HTTPException(
                status_code=409, detail="草稿已经在其他窗口更新，请重新读取后再保存"
            )
        if draft.code == payload.code:
            await db.commit()
            await db.refresh(draft)
            return {
                "task_id": task_id,
                "task_revision": payload.task_revision,
                "scope_key": scope_key,
                "revision_number": draft.revision,
                "code": payload.code,
                "code_hash": code_hash,
                "updated_at": draft.updated_at,
            }
        draft.code = payload.code
        draft.code_sha256 = code_hash
        draft.lesson_session_id = payload.lesson_session_id
        draft.scope_key = scope_key
        draft.revision += 1
    try:
        await db.commit()
    except IntegrityError as caught:
        await db.rollback()
        current = await db.scalar(
            select(CodeDraft).where(
                CodeDraft.owner_user_id == context.user.id,
                CodeDraft.task_id == task_id,
                CodeDraft.task_revision == payload.task_revision,
                CodeDraft.scope_key == scope_key,
            )
        )
        if current is not None:
            raise HTTPException(
                status_code=409,
                detail="草稿已在其他窗口创建，请重新读取后再保存",
            ) from caught
        raise
    await db.refresh(draft)
    return {
        "task_id": task_id,
        "task_revision": payload.task_revision,
        "scope_key": scope_key,
        "revision_number": draft.revision,
        "code": payload.code,
        "code_hash": code_hash,
        "updated_at": draft.updated_at,
    }


@router.post(
    "/code-runs",
    response_model=CodeRunCreateView,
    dependencies=[Depends(csrf_dependency)],
)
async def create_code_run(
    payload: RunCreate,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task_id = request.query_params.get("task_id")
    if not task_id:
        raise HTTPException(status_code=422, detail="缺少 task_id")
    task = await _load_task(db, task_id, payload.task_revision, context.user.id)
    scope_key, _normalized_scope = await _resolve_scope(
        db,
        owner_id=context.user.id,
        scope=payload.scope,
        settings=request.app.state.settings,
        lesson_session_id=payload.lesson_session_id,
        quiz_session_id=payload.quiz_session_id,
        question_id=payload.question_id,
    )
    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    request_hash = _request_hash(task_id=task_id, payload=payload, scope_key=scope_key)
    existing = await db.scalar(
        select(CodeRun).where(
            CodeRun.owner_user_id == context.user.id,
            CodeRun.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.task_id != task_id
            or existing.task_revision != payload.task_revision
            or existing.code_sha256 != code_hash
            or existing.scope_key != scope_key
            or existing.purpose != payload.purpose
            or (existing.request_hash is not None and existing.request_hash != request_hash)
        ):
            raise HTTPException(status_code=409, detail="幂等键已绑定其他代码快照")
        return {
            "run": _run_view(existing, request.app.state.settings, task),
            "idempotent_replay": True,
        }

    # Async requests are durable queue entries.  The worker only claims
    # QUEUED rows; marking them RUNNING here would leave a perfectly valid
    # request invisible to the worker after a refresh or API restart.
    initial_status = "QUEUED" if payload.async_run else "RUNNING"
    run = CodeRun(
        owner_user_id=context.user.id,
        task_id=task_id,
        task_revision=payload.task_revision,
        scope_key=scope_key,
        purpose=payload.purpose,
        quiz_session_id=payload.quiz_session_id,
        question_id=payload.question_id,
        lesson_session_id=payload.lesson_session_id,
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        code=payload.code,
        code_sha256=code_hash,
        status=initial_status,
        execution_status=initial_status,
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError as caught:
        await db.rollback()
        existing = await db.scalar(
            select(CodeRun).where(
                CodeRun.owner_user_id == context.user.id,
                CodeRun.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.task_id != task_id
                or existing.task_revision != payload.task_revision
                or existing.request_hash != request_hash
            ):
                raise HTTPException(status_code=409, detail="幂等键已绑定其他代码快照") from caught
            return {
                "run": _run_view(existing, request.app.state.settings, task),
                "idempotent_replay": True,
            }
        raise
    await db.refresh(run)

    if payload.async_run:
        from app.jobs.codelab_worker import execute_code_run

        if request.app.state.settings.codelab_autorun:
            asyncio.create_task(execute_code_run(request.app.state.settings, run.id))
        return JSONResponse(
            status_code=202,
            content=jsonable_encoder(
                {
                    "run": _run_view(run, request.app.state.settings, task),
                    "idempotent_replay": False,
                }
            ),
        )

    if not request.app.state.settings.codelab_runner_url:
        run.status = "UNAVAILABLE"
        run.execution_status = "UNAVAILABLE"
        run.result = {"error": "RUNNER_UNAVAILABLE"}
        run.completed_at = datetime.now(UTC)
        await db.commit()
        return {
            "run": _run_view(run, request.app.state.settings, task),
            "idempotent_replay": False,
        }

    observations: list[dict[str, Any]] = []
    runner_unavailable = False
    cases = (
        [
            {"case_id": f"example-{index + 1}", "input": item.get("input")}
            for index, item in enumerate(task.examples or [])
            if isinstance(item, dict) and isinstance(item.get("input"), dict)
        ]
        if payload.purpose == "EXAMPLE"
        else [{"case_id": c.case_id, "input": c.input} for c in trusted_cases(task_id)]
    )
    for case in cases:
        observation = await _runner_call(
            request.app.state.settings,
            {
                "case_id": case["case_id"],
                "task_id": task_id,
                "task_revision": payload.task_revision,
                "entrypoint": task.entrypoint,
                "input": case["input"],
                "student_code": payload.code,
                "owner_id": str(context.user.id),
                "lease_id": f"{run.id}-{case['case_id']}",
            },
        )
        if observation.get("error") == "RUNNER_UNAVAILABLE":
            runner_unavailable = True
            break
        observations.append(observation)

    grade = None
    if runner_unavailable:
        run.status = "UNAVAILABLE"
        run.execution_status = "UNAVAILABLE"
        run.result = {"error": "RUNNER_UNAVAILABLE", "observations": observations}
    else:
        if payload.purpose == "GRADE":
            grade = grade_observations(task_id, payload.task_revision, observations)
        statuses = {item.get("execution_status") for item in observations}
        known_statuses = {
            "COMPLETED",
            "STUDENT_EXCEPTION",
            "INVALID_JSON",
            "TIMEOUT",
            "OUTPUT_LIMIT",
            "SYSTEM_ERROR",
            "RUNNER_ERROR",
        }
        if (
            not observations
            or statuses - known_statuses
            or statuses & {"SYSTEM_ERROR", "RUNNER_ERROR"}
        ):
            execution = "SYSTEM_ERROR"
        elif "TIMEOUT" in statuses:
            execution = "TIMEOUT"
        elif "OUTPUT_LIMIT" in statuses:
            execution = "OUTPUT_LIMIT"
        elif statuses & {"STUDENT_EXCEPTION", "INVALID_JSON"}:
            execution = "FAILED"
        elif grade is not None and grade.status == "SYSTEM_ERROR":
            execution = "SYSTEM_ERROR"
        else:
            execution = "SUCCEEDED"
        run.status = execution
        run.execution_status = execution
        if payload.purpose == "EXAMPLE":
            # Examples demonstrate execution only. They never create a
            # trusted score or learning evidence.
            run.correctness_status = "NOT_VERIFIED"
            run.deterministic_score = None
        else:
            run.correctness_status = (
                grade.status if grade.status != "SYSTEM_ERROR" else "NOT_VERIFIED"
            )
            run.deterministic_score = grade.deterministic_score
        run.result = {
            **({"grading": grade.as_dict()} if grade is not None else {}),
            "observations": observations,
        }
        if (
            payload.purpose == "GRADE"
            and payload.lesson_session_id
            and grade is not None
            and grade.status in {"PASSED", "PARTIAL", "FAILED"}
        ):
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
    return {
        "run": _run_view(run, request.app.state.settings, task),
        "idempotent_replay": False,
    }


def _scope_kind(scope_key: str) -> str:
    if scope_key == "standalone":
        return "STANDALONE"
    prefix = scope_key.partition(":")[0]
    return prefix.upper() if prefix in {"chapter", "lesson", "quiz"} else "STANDALONE"


def _scope_source(run: CodeRun, task: CodeTaskRevision) -> dict[str, Any]:
    kind = _scope_kind(run.scope_key)
    label = {
        "STANDALONE": "独立题库",
        "CHAPTER": "章节课程练习",
        "LESSON": "课堂编程练习",
        "QUIZ": "专项练习",
    }[kind]
    binding = task.chapter_binding if isinstance(task.chapter_binding, dict) else {}
    if kind == "CHAPTER":
        label = f"章节课程练习 · {binding.get('course_slug', '课程')}"
    return {"scope_kind": kind, "label": label, "href": None}


@router.get("/code-runs", response_model=CodeRunPage)
async def list_code_runs(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    task_id: str | None = Query(default=None, max_length=64),
    task_revision: int | None = Query(default=None, ge=1),
    purpose: Literal["EXAMPLE", "GRADE"] | None = None,
    scope_kind: Literal["STANDALONE", "CHAPTER", "LESSON", "QUIZ"] | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stage = await _task_stage(db, context.user.id)
    revisions = (await db.scalars(select(CodeTaskRevision))).all()
    tasks_by_key = {
        (row.task_id, row.revision): row for row in revisions if _matches_stage(row, stage)
    }
    visible_ids = {key[0] for key in tasks_by_key}
    if not visible_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    runs = (
        await db.scalars(
            select(CodeRun)
            .where(
                CodeRun.owner_user_id == context.user.id,
                CodeRun.task_id.in_(visible_ids),
            )
            .order_by(CodeRun.created_at.desc(), CodeRun.id.desc())
        )
    ).all()
    query = (q or "").strip().casefold()
    filtered: list[tuple[CodeRun, CodeTaskRevision]] = []
    for run in runs:
        task = tasks_by_key.get((run.task_id, run.task_revision))
        if task is None:
            continue
        if task_id and run.task_id != task_id:
            continue
        if task_revision and run.task_revision != task_revision:
            continue
        if purpose and run.purpose != purpose:
            continue
        if scope_kind and _scope_kind(run.scope_key) != scope_kind:
            continue
        if query and query not in f"{task.title} {run.task_id}".casefold():
            continue
        filtered.append((run, task))
    total = len(filtered)
    summaries = []
    for run, task in filtered[offset : offset + limit]:
        source = _scope_source(run, task)
        summaries.append(
            {
                "id": run.id,
                "task_id": run.task_id,
                "task_revision": run.task_revision,
                "title": task.title,
                "purpose": run.purpose,
                "status": run.status,
                "execution_status": run.execution_status,
                "correctness_status": run.correctness_status,
                "deterministic_score": run.deterministic_score,
                "score_scale": 70,
                "feedback_status": _run_view(run, request.app.state.settings, task).get(
                    "feedback_status"
                ),
                "feedback_source": (run.feedback or {}).get("source"),
                "scope_kind": source["scope_kind"],
                "source_label": source["label"],
                "created_at": run.created_at,
                "completed_at": run.completed_at,
            }
        )
    return {"items": summaries, "total": total, "limit": limit, "offset": offset}


@router.get("/code-runs/{run_id}", response_model=CodeRunDetailView)
async def get_code_run(
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
    task = await _load_task(db, run.task_id, run.task_revision, context.user.id)
    return {
        "run": _run_view(run, request.app.state.settings, task),
        "task_snapshot": {
            "task_id": task.task_id,
            "revision": task.revision,
            "title": task.title,
            "description": task.description,
            "entrypoint": task.entrypoint,
            "examples": task.examples,
            "chapter_binding": task.chapter_binding,
        },
        "source": _scope_source(run, task),
    }


@router.post(
    "/code-runs/{run_id}/cancel",
    response_model=dict[str, CodeRunView],
    dependencies=[Depends(csrf_dependency)],
)
async def cancel_code_run(
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
    task = await _load_task(db, run.task_id, run.task_revision, context.user.id)
    if run.status in {"QUEUED", "RUNNING"}:
        run.status = "CANCELLED"
        run.execution_status = "CANCELLED"
        run.completed_at = datetime.now(UTC)
        await db.commit()
    return {"run": _run_view(run, request.app.state.settings, task)}


@router.post(
    "/code-runs/{run_id}/feedback",
    response_model=CodeFeedbackView,
    dependencies=[Depends(csrf_dependency)],
)
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
    task = await _load_task(db, run.task_id, run.task_revision, context.user.id)
    if run.purpose != "GRADE":
        raise HTTPException(
            status_code=409, detail="公开样例运行没有正式判分，不能请求 AI 判题建议"
        )
    if run.feedback_status == "READY" and (
        (run.feedback or {}).get("facts_version") == _FEEDBACK_FACTS_VERSION
    ):
        return {
            "run": _run_view(run, request.app.state.settings, task),
            "fixture": request.app.state.settings.gateway_mode == "fixture",
        }

    if run.execution_status in {"QUEUED", "RUNNING"}:
        raise HTTPException(status_code=409, detail="运行尚未完成")
    settings = request.app.state.settings
    feedback_eligible, reason = _feedback_eligibility(run, settings)
    if not feedback_eligible:
        return {
            "run": _run_view(run, settings, task),
            "fixture": settings.gateway_mode == "fixture",
            "reason": reason,
        }
    if settings.gateway_mode == "knodo":
        try:
            snapshot = _snapshot_for_run(run=run, task=task, owner_id=str(context.user.id))
            base_request = _code_feedback_request(run=run, task=task)
            payload = build_feedback_request(
                base_request,
                snapshot,
                authenticated_owner_id=str(context.user.id),
            )
        except (FeedbackSnapshotError, KeyError, TypeError, ValueError):
            run.feedback_status = "UNAVAILABLE"
            run.feedback = {
                "status": "UNAVAILABLE",
                "run_id": str(run.id),
                "code_hash": run.code_sha256,
                "summary": "这次运行缺少可供 AI 参考的确定性结果。",
                "references": [],
            }
            await db.commit()
            return {
                "run": _run_view(run, settings, task),
                "fixture": False,
                "reason": "DETERMINISTIC_RESULT_UNAVAILABLE",
            }

        from app.modules.ai.service import target_arguments

        target_options = await target_arguments(
            db, Operation.CODE_FEEDBACK, payload, require_route=settings.gateway_mode == "knodo"
        )
        await db.commit()
        outcome = await request.app.state.gateway.invoke(
            Operation.CODE_FEEDBACK,
            payload,
            **target_options,
            timeout_seconds=settings.gateway_timeout_seconds,
        )
        if outcome.status == GatewayStatus.OK and outcome.output is not None:
            message = str(outcome.output.get("message_markdown", "")).strip()
            problems: list[str] = []
            try:
                # Keep the same output boundary as teaching turns. The Tutor
                # response is advice only and never changes deterministic data.
                from app.modules.teaching.validation import validate_assistant_output

                problems = validate_assistant_output(
                    operation=Operation.CODE_FEEDBACK,
                    payload=outcome.output,
                    context=_code_feedback_validation_context(base_request),
                    fixture_allowance=None,
                )
                if problems or not message:
                    raise FeedbackSnapshotError("unsafe Tutor feedback response")
                feedback = TutorFeedback(
                    status="READY",
                    run_id=str(run.id),
                    code_hash=run.code_sha256,
                    summary=message,
                    references=[],
                )
                validate_feedback(feedback.model_dump(mode="json"), snapshot)
            except (FeedbackSnapshotError, ValueError, TypeError):
                reason = problems[0] if problems else "FEEDBACK_CONTENT_INVALID"
                run.feedback_status = "FAILED"
                run.feedback = {
                    "status": "FAILED",
                    "source": "KNODO",
                    "reason_code": reason,
                    "run_id": str(run.id),
                    "code_hash": run.code_sha256,
                    "summary": "Knodo 返回的代码建议未通过安全校验。",
                    "references": [],
                }
                await db.commit()
                return {
                    "run": _run_view(run, settings, task),
                    "fixture": False,
                    "reason": reason,
                }
            run.feedback_status = "READY"
            run.feedback = {
                **feedback.model_dump(mode="json"),
                "source": "KNODO",
                "facts_version": _FEEDBACK_FACTS_VERSION,
            }
            await db.commit()
            return {"run": _run_view(run, settings, task), "fixture": False}

        run.feedback_status = "FAILED"
        run.feedback = {
            "status": "FAILED",
            "source": "KNODO",
            "reason_code": (
                outcome.error.reason_code
                if outcome.error is not None
                else "KNODO_FEEDBACK_UNAVAILABLE"
            ),
            "run_id": str(run.id),
            "code_hash": run.code_sha256,
            "summary": "暂时无法取得 Knodo 的代码建议，请稍后重试。",
            "references": [],
        }
        await db.commit()
        return {
            "run": _run_view(run, settings, task),
            "fixture": False,
            "reason": (
                outcome.error.reason_code
                if outcome.error is not None
                else "KNODO_FEEDBACK_UNAVAILABLE"
            ),
        }

    if settings.gateway_mode != "fixture":
        run.feedback_status = "UNAVAILABLE"
        await db.commit()
        return {"run": _run_view(run, settings, task), "fixture": False}

    run.feedback_status = "READY"
    run.feedback = {
        "status": "READY",
        "source": "FIXTURE",
        "facts_version": _FEEDBACK_FACTS_VERSION,
        "run_id": str(run.id),
        "code_hash": run.code_sha256,
        "summary": "这是本地合成反馈（非真实 Knodo）；确定性测试结果仍是唯一可信判定。",
        "references": [],
    }
    await db.commit()
    return {"run": _run_view(run, settings, task), "fixture": True}
