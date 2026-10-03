"""Durable, private batches; only completely validated groups become quizzes."""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayStatus
from app.modules.ai.service import target_arguments
from app.modules.assessment.errors import DesignerUnavailable, QuizDraftRejected
from app.modules.assessment.models import GenerationJob
from app.modules.assessment.specs import build_designer_request
from app.modules.assessment.validation import (
    ValidatedQuizDraft,
    build_student_projection,
    validate_quiz_draft,
)


def stem_key(question):
    text = re.sub(r"^\s*(?:第\s*\d+\s*(?:道|个)?题|\d+[.、)）])[:：.、\s]*", "", question["stem"])
    return re.sub(r"[\W_]+", "", text).casefold()


async def generate_batches(factory, *, settings, gateway, job_id, token, material, allowance):
    """Checkpoint each successful call; retries skip already saved batches."""
    async with factory() as db:
        job = await db.get(GenerationJob, job_id)
        config = copy.deepcopy(job.request_config or {})
    total = config.get("question_count")
    if total is None:
        total = {"PRIMARY_LOWER": 1, "PRIMARY_UPPER": 2, "JUNIOR": 3, "SENIOR": 3}[material.stage]
    if isinstance(total, bool) or not isinstance(total, int) or not 1 <= total <= 20:
        raise QuizDraftRejected("题量必须为 1–20 的整数", code="COUNT_NOT_ALLOWED")
    batches = list(config.get("validated_batches") or [])
    all_questions = []
    payload = None
    for number, offset in enumerate(range(0, total, 5)):
        request, expectation = build_designer_request(
            material,
            request_id=f"{config['request_id']}-batch-{number + 1}",
            allowance=allowance,
            question_count=min(5, total - offset),
            difficulty=config.get("difficulty"),
            question_types=config.get("question_types") or None,
            objective_ids=config.get("objective_ids") or None,
        )
        if number < len(batches):
            validated = validate_quiz_draft(batches[number], expectation=expectation)
        else:
            request["quiz_spec"]["misconception_summary"] = (
                (
                    "学生的练习要求（仅作题目偏好，不改变题数、协议或引用）："
                    + config["student_request"][:200]
                    + "。"
                    if config.get("student_request")
                    else ""
                )
                + (
                    "当前阅读位置：" + config["scene"]["visible_section"][:100] + "。"
                    if config.get("scene", {}).get("visible_section")
                    else ""
                )
                + (
                    "学生所选片段（只作问题指向，知识依据仍用knowledge_context）："
                    + config["scene"]["selected_text"][:250]
                    + "。"
                    if config.get("scene", {}).get("selected_text")
                    else ""
                )
                + "本次是同一题组的第 "
                + str(number + 1)
                + " 批，请设计不同的题目。"
                + (
                    " 已有题目，请勿重复：" + "；".join(q["stem"][:45] for q in all_questions)
                    if all_questions
                    else ""
                )
            )[:1500]
            async with factory() as db:
                job = await db.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if job.status != "RUNNING" or job.lease_token != token:
                    return None
                job.lease_expires_at = datetime.now(UTC) + timedelta(
                    seconds=max(
                        600,
                        settings.authoring_lease_seconds,
                        settings.knodo_designer_timeout_seconds + 60,
                    )
                )
                options = await target_arguments(
                    db,
                    Operation.QUIZ_DRAFT,
                    request,
                    require_route=getattr(gateway, "mode", None) == "knodo",
                )
                await db.commit()
            result = await gateway.invoke(
                Operation.QUIZ_DRAFT,
                request,
                timeout_seconds=settings.knodo_designer_timeout_seconds,
                **options,
            )
            if result.status is not GatewayStatus.OK or result.output is None:
                raise DesignerUnavailable(
                    "出题服务未返回可校验题目，请重试补齐剩余题目",
                    code=result.error.reason_code if result.error else "GATEWAY_FAILED",
                )
            validated = validate_quiz_draft(result.output, expectation=expectation)
        seen = {stem_key(q) for q in all_questions}
        for question in validated.questions:
            key = stem_key(question)
            if key in seen:
                raise QuizDraftRejected(
                    "生成了重复题目，请重试补齐当前批次", code="DUPLICATE_QUESTION"
                )
            seen.add(key)
        all_questions.extend(copy.deepcopy(validated.questions))
        payload = copy.deepcopy(validated.payload)
        if number >= len(batches):
            batches.append(validated.payload)
            async with factory() as db:
                job = await db.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if job.status != "RUNNING" or job.lease_token != token:
                    return None
                job.request_config = {**job.request_config, "validated_batches": batches}
                job.request_summary = {
                    **(job.request_summary or {}),
                    "count": total,
                    "generated_count": len(all_questions),
                }
                job.gateway_invocation_id = result.invocation_id
                job.usage = result.usage.model_dump(mode="json")
                await db.commit()
    for index, question in enumerate(all_questions):
        question["question_key"] = f"q{index + 1}"
    payload["request_id"] = config["request_id"]
    payload["questions"] = all_questions
    return ValidatedQuizDraft(payload, tuple(all_questions), build_student_projection(payload))
