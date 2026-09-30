"""Server-owned targets; no client-selected provider URLs or credentials."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import AIConfiguration


# Backend tools are installed by application code, never by a submitted Python path.
@dataclass(frozen=True)
class CapabilityHandler:
    run: Callable[..., Awaitable[Any]]
    input_model: type[BaseModel]
    output_model: type[BaseModel]


BACKEND_HANDLERS: dict[str, CapabilityHandler] = {}


def register_backend_handler(
    name: str,
    handler: Callable[..., Awaitable[Any]],
    *,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
) -> None:
    if name in BACKEND_HANDLERS:
        raise ValueError("duplicate capability handler")
    BACKEND_HANDLERS[name] = CapabilityHandler(handler, input_model, output_model)


def initial_data(settings) -> dict:
    agents = []
    for key, name, role, bot, workspace in [
        (
            "legacy-tutor",
            "霜铃课堂教师（兼容）",
            "teacher",
            settings.knodo_tutor_bot_id,
            settings.knodo_tutor_workspace_id,
        ),
        (
            "designer",
            "霜铃教研制作",
            "designer",
            settings.knodo_designer_bot_id,
            settings.knodo_designer_workspace_id,
        ),
        ("primary", "霜铃·小学教师", "teacher", None, None),
        ("junior", "霜铃·初中教师", "teacher", None, None),
        ("senior", "霜铃·高中教师", "teacher", None, None),
        ("memory", "个人记忆整理助手", "memory", None, None),
    ]:
        agents.append(
            dict(
                id=key,
                name=name,
                role=role,
                description="",
                enabled=bool(bot and workspace),
                bot_id=bot,
                workspace_id=workspace,
                prompt_version="v1",
                remote_memory_disabled=False,
                capabilities=[],
            )
        )
    routes = []
    for operation, agent in [
        ("TEACH_TURN", agents[0]),
        ("CODE_FEEDBACK", agents[0]),
        ("QUIZ_DRAFT", agents[1]),
        ("LESSON_PACKAGE_DRAFT", agents[1]),
    ]:
        if agent["enabled"]:
            routes.append(dict(operation=operation, stage="*", agent_id=agent["id"]))
    return {"agents": agents, "routes": routes, "capabilities": []}


async def initialize(db: AsyncSession, settings) -> None:
    await db.execute(
        insert(AIConfiguration)
        .values(id=1, revision=1, data=initial_data(settings))
        .on_conflict_do_nothing(index_elements=["id"])
    )
    row = await db.get(AIConfiguration, 1)
    legacy = next(
        (a for a in row.data["agents"] if a["id"] == "legacy-tutor" and a["enabled"]), None
    )
    if legacy:
        from app.modules.teaching.models import LessonSession

        await db.execute(
            update(LessonSession)
            .where(LessonSession.teacher_snapshot.is_(None))
            .values(teacher_snapshot=legacy)
        )
    await db.commit()


async def registry(db: AsyncSession, settings=None) -> dict:
    row = await db.get(AIConfiguration, 1)
    return {
        "revision": row.revision if row else 0,
        "persisted": row is not None,
        "data": row.data
        if row
        else (
            initial_data(settings) if settings else {"agents": [], "routes": [], "capabilities": []}
        ),
    }


async def resolve(
    db: AsyncSession,
    operation: str,
    stage: str = "*",
    pinned: dict | None = None,
    *,
    require_route: bool = False,
) -> dict | None:
    config = await registry(db)
    data = config["data"]
    agent_id = pinned.get("id") if pinned else None
    if not agent_id:
        choices = [
            r for r in data["routes"] if r["operation"] == operation and r["stage"] in (stage, "*")
        ]
        choices.sort(key=lambda r: r["stage"] == "*")
        if not choices:
            if require_route and config["persisted"]:
                raise ValueError("该任务和学段尚未配置可用助手")
            return None
        agent_id = choices[0]["agent_id"]
    agent = next((a for a in data["agents"] if a["id"] == agent_id), None)
    if not agent or not agent["enabled"]:
        raise ValueError("所选 AI 助手已停用，请创建新的对话")
    if not agent.get("bot_id") or not agent.get("workspace_id"):
        raise ValueError("AI 助手尚未完成连接配置")
    expected_role = {
        "TEACH_TURN": "teacher",
        "CODE_FEEDBACK": "teacher",
        "QUIZ_DRAFT": "designer",
        "LESSON_PACKAGE_DRAFT": "designer",
        "MEMORY_EXTRACT": "memory",
    }.get(operation)
    if agent["role"] != expected_role:
        raise ValueError("助手职责与当前任务不匹配")
    signature = target_signature(agent)
    return {**agent, "configuration_revision": config["revision"], "signature": signature}


def public_teacher(snapshot: dict | None) -> dict | None:
    return (
        {k: snapshot[k] for k in ("id", "name", "description") if k in snapshot}
        if snapshot
        else None
    )


async def target_arguments(
    db: AsyncSession, operation, payload: dict, *, require_route=False
) -> dict:
    from app.integrations.knodo.wire import KnodoTarget

    stage = payload.get("stage") or (payload.get("learner") or {}).get("stage", "*")
    target = await resolve(db, str(operation), stage, require_route=require_route)
    return (
        {"target": KnodoTarget(bot_id=target["bot_id"], workspace_id=target["workspace_id"])}
        if target
        else {}
    )


async def execute_backend_capability(
    db: AsyncSession, capability_id: str, payload: Any, context: dict
):
    """Future business tools receive only declared context, not arbitrary student/global state."""
    config = await registry(db)
    cap = next((c for c in config["data"]["capabilities"] if c["id"] == capability_id), None)
    if not cap or not cap["enabled"] or cap["executor"] != "BACKEND":
        raise ValueError("capability unavailable")
    handler = BACKEND_HANDLERS.get(cap.get("handler"))
    if handler is None:
        raise ValueError("capability handler not installed")
    allowed = {key: value for key, value in context.items() if key in cap["allowed_context"]}
    request = handler.input_model.model_validate(payload)
    result = await handler.run(request, allowed)
    return handler.output_model.model_validate(result)


async def inspect_remote_memory(settings, workspace_id: str) -> dict:
    """Read documented workspace details without exposing unrelated workspace data."""
    import os

    import httpx

    if settings.gateway_mode != "knodo":
        return {"verified": False, "reason": "不是 Knodo 模式"}
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = await client.get(
                f"{settings.knodo_base_url.rstrip('/')}/api/v1/workspaces/{workspace_id}",
                headers={
                    "Authorization": "Bearer " + os.environ.get(settings.knodo_token_env_var, "")
                },
            )
            response.raise_for_status()
            body = response.json()
        data = body.get("data", body)
        legacy, plugin = data.get("memoryEnabled"), data.get("memoryPluginEnabled")
        return {
            "verified": True,
            "legacy_enabled": legacy if isinstance(legacy, bool) else None,
            "plugin_enabled": plugin if isinstance(plugin, bool) else None,
            "both_explicitly_disabled": legacy is False and plugin is False,
        }
    except (httpx.HTTPError, ValueError, AttributeError):
        return {"verified": False, "reason": "无法读取空间记忆配置"}


def target_signature(agent: dict) -> str:
    execution = {
        key: agent.get(key)
        for key in ("id", "role", "bot_id", "workspace_id", "prompt_version", "capabilities")
    }
    return hashlib.sha256(json.dumps(execution, sort_keys=True).encode()).hexdigest()[:20]
