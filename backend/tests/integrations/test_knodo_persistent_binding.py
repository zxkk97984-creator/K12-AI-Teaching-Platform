"""T13-local: durable, owner/session/target-scoped Knodo continuation bindings."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.integrations.knodo.fixture import teaching_response_payload
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayResult, GatewayStatus, GatewayUsage
from app.jobs import teaching_worker
from app.modules.teaching.models import AgentRun, RemoteBinding, RunStatus
from app.modules.teaching.service import create_free_session, create_session, create_turn
from tests.identity_helpers import create_synthetic_user
from tests.teaching_helpers import prepare_fixture_course, teaching_settings


class SyntheticKnodoGateway:
    """No network: behaves like Knodo only at the persisted binding boundary."""

    def __init__(self, scope: str, *, fail_first: bool = False):
        self.scope = scope
        self.fail_first = fail_first
        self.calls: list[tuple[str, str | None]] = []

    def continuation_scope(self, operation: Operation) -> str:
        return self.scope

    async def invoke(
        self,
        operation: Operation,
        request: dict,
        *,
        remote_conversation_id: str | None = None,
        **kwargs,
    ) -> GatewayResult:
        session_id = request["lesson_session_id"]
        self.calls.append((session_id, remote_conversation_id))
        conversation_id = remote_conversation_id or f"conv-{session_id}"
        payload = teaching_response_payload(Operation(operation), request)
        source = request["knowledge_context"][0]
        payload["source_refs"] = [
            {
                "source_id": source["source_id"],
                "revision": source["revision"],
                "locator": source["locator"],
            }
        ]
        payload["action"] = None
        metadata = {
            "provider": "knodo",
            "role": "tutor",
            "bot_id": "synthetic-tutor-bot",
            "workspace_id": "synthetic-classroom",
            "completion_id": f"completion-{len(self.calls)}",
            "conversation_id": conversation_id,
            "model": "synthetic-model",
            "finish_reason": "stop",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }
        should_fail = self.fail_first and len(self.calls) == 1
        return GatewayResult(
            invocation_id=str(uuid.uuid4()),
            operation=operation,
            mode="knodo",
            status=GatewayStatus.FAILED if should_fail else GatewayStatus.OK,
            output=None if should_fail else payload,
            error=None,
            usage=GatewayUsage(
                input_bytes=1,
                output_bytes=1,
                duration_ms=1,
                upstream_calls=1,
            ),
            remote_metadata=metadata,
            fixture=False,
        )


async def _student(settings: Settings, username: str):
    return await create_synthetic_user(
        settings,
        username=username,
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )


async def _run_turn(db, settings, gateway, *, user, session, key: str) -> AgentRun:
    run, created = await create_turn(
        db,
        user=user,
        session=session,
        operation=Operation.TEACH_TURN.value,
        message=f"合成消息 {key}",
        idempotency_key=key,
    )
    assert created is True
    status = await teaching_worker.execute_run(settings, gateway, str(run.id))
    refreshed = await db.scalar(
        select(AgentRun).where(AgentRun.id == run.id).execution_options(populate_existing=True)
    )
    assert refreshed is not None
    assert status == refreshed.status
    return refreshed


@pytest.mark.asyncio
async def test_second_turn_reuses_only_the_same_session_target_binding(
    content_session,
    test_settings: Settings,
) -> None:
    settings = teaching_settings(test_settings, gateway_mode="disabled")
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t13.binding.owner")
    session = await create_session(
        content_session,
        settings=settings,
        user=user,
        chapter_id=revision.chapter_id,
    )
    gateway = SyntheticKnodoGateway("scope:tutor:v1")

    first = await _run_turn(
        content_session, settings, gateway, user=user, session=session, key="binding-first"
    )
    second = await _run_turn(
        content_session, settings, gateway, user=user, session=session, key="binding-second"
    )

    assert first.status == second.status == RunStatus.SUCCEEDED.value
    assert gateway.calls == [
        (str(session.id), None),
        (str(session.id), f"conv-{session.id}"),
    ]
    bindings = list(
        await content_session.scalars(
            select(RemoteBinding).order_by(RemoteBinding.created_at, RemoteBinding.id)
        )
    )
    assert [item.remote_id for item in bindings] == [
        f"conv-{session.id}",
        f"conv-{session.id}",
    ]
    assert {item.remote_scope for item in bindings} == {"scope:tutor:v1"}
    assert all(item.remote_metadata["bot_id"] == "synthetic-tutor-bot" for item in bindings)


@pytest.mark.asyncio
async def test_two_synthetic_students_never_cross_reuse_remote_conversations(
    content_session,
    test_settings: Settings,
) -> None:
    settings = teaching_settings(test_settings, gateway_mode="disabled")
    revision = await prepare_fixture_course(content_session)
    student_a = await _student(settings, "t13.binding.a")
    student_b = await _student(settings, "t13.binding.b")
    session_a = await create_session(
        content_session, settings=settings, user=student_a, chapter_id=revision.chapter_id
    )
    session_b = await create_session(
        content_session, settings=settings, user=student_b, chapter_id=revision.chapter_id
    )
    gateway = SyntheticKnodoGateway("scope:tutor:v1")

    await _run_turn(
        content_session, settings, gateway, user=student_a, session=session_a, key="student-a-1"
    )
    await _run_turn(
        content_session, settings, gateway, user=student_b, session=session_b, key="student-b-1"
    )
    await _run_turn(
        content_session, settings, gateway, user=student_a, session=session_a, key="student-a-2"
    )
    await _run_turn(
        content_session, settings, gateway, user=student_b, session=session_b, key="student-b-2"
    )

    assert gateway.calls == [
        (str(session_a.id), None),
        (str(session_b.id), None),
        (str(session_a.id), f"conv-{session_a.id}"),
        (str(session_b.id), f"conv-{session_b.id}"),
    ]


@pytest.mark.asyncio
async def test_changed_target_scope_starts_a_new_remote_conversation(
    content_session,
    test_settings: Settings,
) -> None:
    settings = teaching_settings(test_settings, gateway_mode="disabled")
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t13.binding.target-change")
    session = await create_session(
        content_session, settings=settings, user=user, chapter_id=revision.chapter_id
    )
    original = SyntheticKnodoGateway("scope:tutor:v1")
    changed = SyntheticKnodoGateway("scope:tutor:v2")

    await _run_turn(
        content_session, settings, original, user=user, session=session, key="target-before"
    )
    await _run_turn(
        content_session, settings, changed, user=user, session=session, key="target-after"
    )

    assert original.calls == [(str(session.id), None)]
    assert changed.calls == [(str(session.id), None)]


@pytest.mark.asyncio
async def test_failed_accepted_turn_is_audited_but_not_reused(
    content_session,
    test_settings: Settings,
) -> None:
    settings = teaching_settings(test_settings, gateway_mode="disabled")
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t13.binding.failed")
    session = await create_session(
        content_session, settings=settings, user=user, chapter_id=revision.chapter_id
    )
    gateway = SyntheticKnodoGateway("scope:tutor:v1", fail_first=True)

    first = await _run_turn(
        content_session, settings, gateway, user=user, session=session, key="accepted-invalid"
    )
    second = await _run_turn(
        content_session, settings, gateway, user=user, session=session, key="after-invalid"
    )

    assert first.status == RunStatus.FAILED.value
    assert second.status == RunStatus.SUCCEEDED.value
    assert gateway.calls == [(str(session.id), None), (str(session.id), None)]
    failed_binding = await content_session.scalar(
        select(RemoteBinding).where(RemoteBinding.run_id == first.id)
    )
    assert failed_binding is not None
    assert failed_binding.remote_id == f"conv-{session.id}"
    assert failed_binding.remote_metadata["completion_id"] == "completion-1"


@pytest.mark.asyncio
async def test_free_chat_replays_bounded_local_history_when_stream_has_no_conversation_id(
    content_session, test_settings: Settings
) -> None:
    settings = teaching_settings(test_settings, gateway_mode="disabled")
    user = await _student(settings, "t13.binding.no-stream-id")
    session = await create_free_session(content_session, settings=settings, user=user)

    class NoConversationIdGateway:
        def __init__(self):
            self.requests: list[dict] = []

        def continuation_scope(self, _operation):
            return "scope:tutor:stream-test"

        async def invoke(self, operation, request, **_kwargs):
            self.requests.append(request)
            output = teaching_response_payload(Operation(operation), request)
            output["message_markdown"] = f"第{len(self.requests)}轮答复"
            output["source_refs"] = []
            output["evidence_refs"] = []
            output["action"] = None
            return GatewayResult(
                invocation_id=str(uuid.uuid4()),
                operation=Operation(operation),
                mode="knodo",
                status=GatewayStatus.OK,
                output=output,
                error=None,
                usage=GatewayUsage(input_bytes=1, output_bytes=1, duration_ms=1, upstream_calls=1),
                remote_metadata={"conversation_id": None},
                fixture=False,
            )

    gateway = NoConversationIdGateway()
    scene = {"page_type": "conversation", "route": "/conversations"}
    first, _ = await create_turn(
        content_session,
        user=user,
        session=session,
        operation=Operation.TEACH_TURN.value,
        message="第一轮问题",
        idempotency_key="no-id-first",
        scene_snapshot=scene,
    )
    assert await teaching_worker.execute_run(settings, gateway, str(first.id)) == "SUCCEEDED"
    second, _ = await create_turn(
        content_session,
        user=user,
        session=session,
        operation=Operation.TEACH_TURN.value,
        message="第二轮追问",
        idempotency_key="no-id-second",
        scene_snapshot=scene,
    )
    assert await teaching_worker.execute_run(settings, gateway, str(second.id)) == "SUCCEEDED"

    assert len(gateway.requests) == 2
    assert gateway.requests[0]["student_input"].endswith("第一轮问题")
    assert "先前对话记录" not in gateway.requests[0]["student_input"]
    followup = gateway.requests[1]["student_input"]
    assert "第一轮问题" in followup
    assert "第1轮答复" in followup
    assert followup.endswith("第二轮追问")
    assert len(followup) <= 8000
    assert (
        await content_session.scalar(select(RemoteBinding).where(RemoteBinding.run_id == first.id))
    ) is None

    practice, _ = await create_turn(
        content_session,
        user=user,
        session=session,
        operation=Operation.TEACH_TURN.value,
        message="练习页继续问",
        idempotency_key="no-id-practice-third",
        scene_snapshot={"page_type": "practice", "route": "/practice"},
    )
    assert await teaching_worker.execute_run(settings, gateway, str(practice.id)) == "SUCCEEDED"
    assert "第一轮问题" in gateway.requests[2]["student_input"]
    assert gateway.requests[2]["student_input"].endswith("练习页继续问")

    long_message = "长" * 8000
    long_turn, _ = await create_turn(
        content_session,
        user=user,
        session=session,
        operation=Operation.TEACH_TURN.value,
        message=long_message,
        idempotency_key="no-id-long-fourth",
        scene_snapshot=scene,
    )
    assert await teaching_worker.execute_run(settings, gateway, str(long_turn.id)) == "SUCCEEDED"
    assert gateway.requests[3]["student_input"] == long_message
