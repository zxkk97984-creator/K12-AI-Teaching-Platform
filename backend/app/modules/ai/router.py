import json
import os
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.ai.models import AIConfiguration
from app.modules.ai.schemas import RegistryUpdate, RegistryView
from app.modules.ai.service import (
    BACKEND_HANDLERS,
    inspect_remote_memory,
    registry,
    target_signature,
)
from app.modules.identity.dependencies import csrf_dependency, require_admin

router = APIRouter(
    prefix="/admin/ai", tags=["ai-administration"], dependencies=[Depends(require_admin)]
)


@router.get("/configuration", response_model=RegistryView)
async def read_configuration(request: Request, db: AsyncSession = Depends(get_session)):
    return await registry(db, request.app.state.settings)


@router.put("/configuration", response_model=RegistryView, dependencies=[Depends(csrf_dependency)])
async def write_configuration(
    body: RegistryUpdate, request: Request, db: AsyncSession = Depends(get_session)
):
    settings = request.app.state.settings
    checked_spaces = set()
    previous = await registry(db, settings)
    proofs = previous["data"].get("verifications", {})
    if settings.gateway_mode == "knodo":
        routed = {route.agent_id for route in body.data.routes}
        for agent in body.data.agents:
            if agent.id not in routed or agent.id == "legacy-tutor" or agent.role == "designer":
                continue
            proof = proofs.get(agent.id, {})
            if proof.get("status") != "PASSED" or proof.get("signature") != target_signature(
                agent.model_dump()
            ):
                raise HTTPException(
                    422, "请先保存未启用的助手，并完成连接与输出协议测试，再设置路由"
                )
            if agent.workspace_id not in checked_spaces:
                memory = await inspect_remote_memory(settings, agent.workspace_id)
                if not memory.get("both_explicitly_disabled"):
                    raise HTTPException(
                        422, ("新教师或记忆助手的空间必须将两套远端记忆明确禁用，并通过 API 核验")
                    )
                checked_spaces.add(agent.workspace_id)
    for cap in body.data.capabilities:
        if cap.executor == "BACKEND" and cap.enabled and cap.handler not in BACKEND_HANDLERS:
            raise HTTPException(422, "后端处理器尚未安装；可先停用登记")
    new_data = body.data.model_dump()
    new_data["verifications"] = {
        key: value for key, value in proofs.items() if key in {a.id for a in body.data.agents}
    }
    if body.base_revision == 0:
        inserted = await db.scalar(
            insert(AIConfiguration)
            .values(id=1, revision=1, data=new_data)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(AIConfiguration.id)
        )
        if inserted is None:
            raise HTTPException(409, "配置已被更新，请刷新")
    else:
        row = await db.scalar(
            select(AIConfiguration).where(AIConfiguration.id == 1).with_for_update()
        )
        if row is None or row.revision != body.base_revision:
            raise HTTPException(409, "配置已被更新，请刷新")
        row.data = new_data
        row.revision += 1
    await db.commit()
    return await registry(db)


@router.post("/agents/{agent_id}/verify", dependencies=[Depends(csrf_dependency)])
async def verify_binding(
    agent_id: str, request: Request, db: AsyncSession = Depends(get_session)
) -> dict:
    config = await registry(db, request.app.state.settings)
    agent = next((a for a in config["data"]["agents"] if a["id"] == agent_id), None)
    if not agent or not agent.get("workspace_id"):
        raise HTTPException(422, "请先填写并保存工作空间")
    settings = request.app.state.settings
    if settings.gateway_mode != "knodo":
        return {"status": "NOT_VERIFIED", "reason": "当前不是 Knodo 模式", "plugins": []}
    memory_status = await inspect_remote_memory(settings, agent["workspace_id"])
    headers = {"Authorization": "Bearer " + os.environ.get(settings.knodo_token_env_var, "")}
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = await client.get(
                f"{settings.knodo_base_url.rstrip('/')}/api/v1/workspaces/{agent['workspace_id']}/plugins",
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
        payload = body.get("data", body) if isinstance(body, dict) else body
        rows = (
            payload.get("list", payload.get("plugins", []))
            if isinstance(payload, dict)
            else payload
        )
        if not isinstance(rows, list):
            raise ValueError("invalid plugin list")
        plugins = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            plugin = entry.get("plugin", entry)
            if isinstance(plugin, dict):
                plugins.append(
                    {
                        k: str(plugin[k])[:160]
                        for k in ("id", "name", "version", "status")
                        if k in plugin
                    }
                )
        return {
            "status": "WORKSPACE_READ_VERIFIED",
            "memory": memory_status,
            "checked_at": datetime.now(UTC).isoformat(),
            "plugins": plugins,
            "notice": "仅核实空间插件列表；助手个人技能、提示词与远端记忆开关需在 Knodo 核对。",
        }
    except (httpx.HTTPError, ValueError):
        return {
            "status": "NOT_VERIFIED",
            "reason": "无法读取空间插件，请检查权限和连接",
            "memory": memory_status,
            "plugins": [],
        }


@router.get("/agents/{agent_id}/prompt-template")
async def prompt_template(
    agent_id: str, request: Request, db: AsyncSession = Depends(get_session)
) -> dict:
    """Explicit local assets only; no user-supplied path or remote fetch."""
    from pathlib import Path

    config = await registry(db, request.app.state.settings)
    agent = next((a for a in config["data"]["agents"] if a["id"] == agent_id), None)
    if agent is None:
        raise HTTPException(404, "助手不存在")
    root = Path(__file__).resolve().parents[4] / "platform/knodo"
    if agent["role"] == "memory":
        path = root / "memory/v1/system-prompt.md"
    elif agent["role"] == "designer":
        path = root / "designer/v1/system-prompt.md"
    elif agent_id in {"primary", "junior", "senior"}:
        path = root / "tutor/v1/stages" / (agent_id + ".md")
    else:
        path = root / "tutor/v1/system-prompt.md"
    return {
        "prompt": path.read_text(),
        "notice": ("这是本地配置模板，请粘贴到 Knodo 对应助手的系统提示词。它不表示远端当前内容。"),
    }


@router.post("/agents/{agent_id}/probe", dependencies=[Depends(csrf_dependency)])
async def probe_agent(
    agent_id: str, request: Request, db: AsyncSession = Depends(get_session)
) -> dict:
    from pathlib import Path

    from app.integrations.knodo.wire import KnodoTarget
    from app.modules.ai.extraction import ExtractionFailure, extract
    from app.modules.memory.contracts import ExtractionRequest, SourceMessage

    config = await registry(db, request.app.state.settings)
    agent = next((a for a in config["data"]["agents"] if a["id"] == agent_id), None)
    if (
        agent is None
        or not agent.get("bot_id")
        or not agent.get("workspace_id")
        or not config["persisted"]
    ):
        raise HTTPException(422, "请先填写并保存 Bot ID 和工作空间 ID")
    settings = request.app.state.settings
    if settings.gateway_mode != "knodo":
        return {"status": "NOT_VERIFIED", "reason": "当前不是 Knodo 模式；模拟调用不算远端验证"}
    memory = await inspect_remote_memory(settings, agent["workspace_id"])
    if agent["role"] != "designer" and not memory.get("both_explicitly_disabled"):
        raise HTTPException(422, "请先将工作空间的两套远端记忆都明确禁用")
    signature = target_signature(agent)
    await db.commit()  # Never keep a database transaction open during inference.
    reason = None
    passed = False
    probe_id = str(uuid.uuid4())
    if agent["role"] == "memory":
        source = SourceMessage(
            id="synthetic-probe",
            session_id="synthetic-probe-session",
            observed_at=datetime.now(UTC).isoformat(),
            text="这是合成测试账号的验证消息。我喜欢观察星星。",
        )
        try:
            output = await extract(
                settings,
                ExtractionRequest(request_id=probe_id, sources=[source]),
                {**agent, "remote_memory_disabled": True},
            )
            passed = any(
                f.source_message_id == source.id and f.quote in source.text for f in output.facts
            )
            if not passed:
                reason = "没有返回带有效来源的记忆条目"
        except ExtractionFailure as exc:
            reason = exc.reason
    else:
        root = Path(__file__).resolve().parents[4] / "contracts/examples"
        filename = (
            "teaching-request.json" if agent["role"] == "teacher" else "designer-request.json"
        )
        payload = json.loads((root / filename).read_text())
        payload["request_id"] = probe_id
        if agent["role"] == "teacher":
            payload["learner"].update(
                {
                    "stage": {"junior": "JUNIOR", "senior": "SENIOR"}.get(
                        agent_id, "PRIMARY_LOWER"
                    ),
                    "grade": {"junior": 8, "senior": 11}.get(agent_id, 2),
                }
            )
        operation = "TEACH_TURN" if agent["role"] == "teacher" else "QUIZ_DRAFT"
        outcome = await request.app.state.gateway.invoke(
            operation,
            payload,
            target=KnodoTarget(bot_id=agent["bot_id"], workspace_id=agent["workspace_id"]),
        )
        passed = outcome.status.value == "OK" and outcome.output is not None
        reason = outcome.error.reason_code if outcome.error else None
    proof = {
        "status": "PASSED" if passed else "FAILED",
        "signature": signature,
        "checked_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "mode": "knodo",
    }
    row = await db.scalar(
        select(AIConfiguration)
        .where(AIConfiguration.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current = next((a for a in row.data["agents"] if a["id"] == agent_id), None) if row else None
    if current is None or target_signature(current) != signature:
        raise HTTPException(409, "测试期间助手配置变化，请重新测试")
    row.data = {**row.data, "verifications": {**row.data.get("verifications", {}), agent_id: proof}}
    row.revision += 1
    await db.commit()
    return proof
