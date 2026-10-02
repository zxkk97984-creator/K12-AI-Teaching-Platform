"""One batch only. An interrupted leased run is recovered as STALE, never replayed."""

import re
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import text

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayStatus
from app.modules.ai.service import execute_backend_capability
from app.modules.lookup.schemas import LookupCard, LookupPlan, LookupResult
from app.modules.lookup.service import LABELS, LookupRuntime
from app.modules.teaching.models import AgentRun
from app.modules.teaching.validation import validate_assistant_output


def planning_context():
    return {
        "schema_version": "k12.lookup.context.v1",
        "phase": "PLAN",
        "tools": list(LABELS),
        "max_queries": 3,
        "results": [],
    }


def unwrap_final(output):
    if isinstance(output, dict) and output.get("kind") == "final":
        return output["response"]
    return output


async def _active(factory, run_id, lease_token, signal):
    if signal is not None and signal.is_set():
        return False
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        return bool(
            run
            and run.status == "RUNNING"
            and run.lease_token == lease_token
            and not run.cancel_requested_at
            and run.lease_expires_at
            and run.lease_expires_at > datetime.now(UTC)
        )


def status_card(result):
    return LookupCard(
        id=f"lookup:status:{result.tool}",
        tool=result.tool,
        kind={
            "COURSE_SEARCH": "COURSE",
            "WRONG_QUESTIONS": "WRONG_QUESTION",
            "LEARNING_PROGRESS": "PROGRESS",
        }[result.tool],
        status=result.status,
        title=LABELS[result.tool],
        description=result.summary,
        queried_at=result.queried_at,
    ).model_dump(mode="json")


def _local_final(request, results, *, notice=None):
    summaries = "\n\n".join(f"{LABELS[result.tool]}：{result.summary}" for result in results)
    return {
        "schema_version": "k12.teaching.response.v1",
        "request_id": request["request_id"],
        "lesson_session_id": request["lesson_session_id"],
        "base_revision": request["base_revision"],
        "curriculum_revision": request["curriculum_revision"],
        "message_markdown": (notice or "已按你的当前账号查询。请查看下面的结果和查询时间。")
        + (f"\n\n{summaries}" if summaries else ""),
        "source_refs": [],
        "evidence_refs": [],
        "followup_question": None,
        "action": None,
        "phase_suggestion": None,
        "warnings": [],
    }


async def complete_lookup_round(
    first,
    *,
    request,
    gateway,
    factory,
    settings,
    run_id,
    lease_token,
    owner_user_id,
    expected_stage,
    signal,
    target,
    context,
    allowance,
    invoke_args,
):
    if first.status is not GatewayStatus.OK or not first.output:
        return first, []
    if first.output.get("kind") != "lookup_request":
        return first.model_copy(update={"output": unwrap_final(first.output)}), []
    try:
        plan = LookupPlan.model_validate(first.output)
        if (
            plan.request_id != request["request_id"]
            or plan.lesson_session_id != request["lesson_session_id"]
            or plan.base_revision != request["base_revision"]
        ):
            raise ValueError("query request does not match the leased turn")
    except (ValueError, ValidationError):
        fallback = _local_final(request, [], notice="查询请求不符合约定，本次未执行。请重新提问。")
        return first.model_copy(update={"output": fallback}), []

    results = []
    for query in plan.queries:
        if not await _active(factory, run_id, lease_token, signal):
            return first.model_copy(update={"status": GatewayStatus.CANCELLED, "output": None}), []
        now = datetime.now(UTC).isoformat()
        try:
            async with factory() as db:
                # Database-enforced read only; each failure rolls back its own transaction.
                await db.execute(text("SET TRANSACTION READ ONLY"))
                await db.execute(text("SET LOCAL statement_timeout = '5s'"))
                runtime = LookupRuntime(db, owner_user_id, expected_stage, settings)
                value = await execute_backend_capability(
                    db,
                    query.tool,
                    query.parameters.model_dump(),
                    {},
                    runtime=runtime,
                )
        except ValueError:
            value = LookupResult(
                tool=query.tool,
                status="UNAVAILABLE",
                queried_at=now,
                summary="功能暂不可用，请核对当前学段后重新提问。",
            )
        except Exception:
            # No exception text / SQL / credentials in model context or stored cards.
            value = LookupResult(
                tool=query.tool,
                status="FAILED",
                queried_at=now,
                summary="查询失败，请稍后重新提问。",
            )
        results.append(value)
    cards = [
        card
        for result in results
        for card in [status_card(result), *(item.model_dump(mode="json") for item in result.cards)]
    ]
    if not await _active(factory, run_id, lease_token, signal):
        return first.model_copy(update={"status": GatewayStatus.CANCELLED, "output": None}), []
    followup = {
        **request,
        "lookup_context": {
            "schema_version": "k12.lookup.context.v1",
            "phase": "FINAL",
            "tools": [],
            "max_queries": 0,
            "results": [result.model_dump(mode="json") for result in results],
        },
    }
    metadata = first.remote_metadata or {}
    args = {
        **invoke_args,
        "remote_conversation_id": metadata.get("conversation_id"),
        "on_content": None,
    }

    # Stream the final pass internally without publishing unchecked query prose.
    async def silent_content(_text):
        return None

    args["on_content"] = silent_content
    second = await gateway.invoke(
        Operation.TEACH_TURN.value, followup, **({"target": target} if target else {}), **args
    )
    if second.status is GatewayStatus.CANCELLED:
        return second, []
    explanation = unwrap_final(second.output)
    sources = [card["source_ref"] for card in cards if card.get("source_ref")]
    trusted_context = {**context, "allowed_source_ids": [ref["source_id"] for ref in sources]}
    valid = (
        second.status is GatewayStatus.OK
        and explanation
        and explanation.get("kind") != "lookup_request"
        and not validate_assistant_output(
            operation=Operation.TEACH_TURN,
            payload=explanation,
            context=trusted_context,
            fixture_allowance=allowance,
        )
    )
    if valid:
        valid = all(ref in sources for ref in explanation.get("source_refs", []))
        valid = valid and all(
            explanation.get(key) == request[key]
            for key in ("request_id", "lesson_session_id", "base_revision", "curriculum_revision")
        )
        # Statistical values and URLs must come from local cards. Reject model-made ones,
        # as well as forged card fields (already rejected by the strict semantic schema).
        prose = explanation.get("message_markdown", "")
        valid = valid and not re.search(
            r"[0-9]|https?://|\]\(|www\.|/(?:courses|chapters|practice|code|resources)",
            prose,
            re.IGNORECASE,
        )
    if any(result.status in ("EMPTY", "FAILED", "UNAVAILABLE") for result in results):
        valid = False
    if not valid:
        notice = "已完成本轮查询；请以卡片中的状态和记录为准。可以重新提问重试。"
        if second.status is not GatewayStatus.OK:
            notice = "查询已结束，老师的解释暂不可用。请查看本地结果，或重新提问。"
        if second.output and second.output.get("kind") == "lookup_request":
            notice = "本次查询已结束，老师再次请求查询已被拒绝。请查看卡片，或重新提问。"
        explanation = _local_final(request, results, notice=notice)
    else:
        explanation = {
            **explanation,
            "action": None,
            "followup_question": None,
            "phase_suggestion": None,
            "source_refs": [],
            "evidence_refs": [],
        }
    # Every model-derived reference is discarded. The stored source list is local too.
    explanation["source_refs"] = sources[:8]
    return second.model_copy(
        update={
            "status": GatewayStatus.OK,
            "error": None,
            "output": explanation,
            "usage": second.usage.model_copy(
                update={
                    "input_bytes": first.usage.input_bytes + second.usage.input_bytes,
                    "output_bytes": first.usage.output_bytes + second.usage.output_bytes,
                    "duration_ms": first.usage.duration_ms + second.usage.duration_ms,
                    "upstream_calls": first.usage.upstream_calls + second.usage.upstream_calls,
                }
            ),
        }
    ), cards
