"""Real local request assembly with a recording synthetic Knodo continuation boundary."""

import json
import uuid
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.integrations.knodo.operations import Operation
from app.jobs.teaching_worker import execute_run
from app.modules.ai.teaching_context import build_runtime_context
from app.modules.memory.automatic import apply_extraction, item_action, settings_update, utcnow
from app.modules.memory.automatic_models import PersonalMemoryItem
from app.modules.memory.contracts import SourceMessage
from app.modules.memory.service import create_document
from app.modules.teaching.models import ConversationMessage
from app.modules.teaching.service import create_free_session, create_turn
from tests.teaching_helpers import create_app_client, teaching_settings
from tests.test_automatic_memory import saved_source, student
from tests.test_memory_reliability import with_summary


@pytest.mark.asyncio
async def test_teacher_payload_history_and_binding_follow_correction_forget_and_use_switch(
    content_session,
    test_settings,
):
    db = content_session
    settings = teaching_settings(test_settings)
    owner = await student(settings, "boundary.owner")
    other = await student(settings, "boundary.other")
    session = await create_free_session(db, settings=settings, user=owner)
    other_session = await create_free_session(db, settings=settings, user=other)
    client = create_app_client(settings)
    fixture_gateway = client._transport.app.state.gateway

    class RecordingGateway:
        calls = []

        def continuation_scope(self, *_args, **_kwargs):
            return "synthetic:a5:teacher"

        async def invoke(self, operation, request, *, remote_conversation_id=None, **kwargs):
            self.calls.append((deepcopy(request), remote_conversation_id))
            result = await fixture_gateway.invoke(operation, request, **kwargs)
            return result.model_copy(
                update={
                    "mode": "knodo",
                    "fixture": False,
                    "remote_metadata": {
                        "conversation_id": remote_conversation_id
                        or "synthetic:" + str(uuid.uuid4())
                    },
                }
            )

    gateway = RecordingGateway()

    async def turn(user, target, message):
        run, _ = await create_turn(
            db,
            user=user,
            session=target,
            operation="TEACH_TURN",
            message=message,
            idempotency_key=str(uuid.uuid4()),
        )
        assert await execute_run(settings, gateway, str(run.id)) == "SUCCEEDED"
        return run

    try:
        initial = await turn(owner, session, "我喜欢天文。")
        message = await db.scalar(
            select(ConversationMessage).where(
                ConversationMessage.run_id == initial.id,
                ConversationMessage.role == "USER",
            )
        )
        s = SourceMessage(
            id=str(message.id),
            session_id=str(message.session_id),
            text=message.content_markdown,
            observed_at=message.created_at.isoformat(),
        )
        await apply_extraction(db, owner.id, with_summary(s, text="喜欢天文"), [s])
        await db.commit()
        await turn(owner, session, "请结合我的兴趣解释人工智能。")
        assert "天文" in json.dumps(gateway.calls[-1][0]["personal_context"], ensure_ascii=False)
        await turn(owner, session, "请结合我的兴趣解释人工智能。")
        assert gateway.calls[-1][1] is not None
        item = await db.scalar(select(PersonalMemoryItem))
        await item_action(
            db, owner.id, item.id, base_revision=1, action="EDIT", statement="喜欢生物"
        )
        await turn(owner, session, "请结合我的兴趣解释人工智能。")
        corrected = json.dumps(gateway.calls[-1][0], ensure_ascii=False)
        assert "生物" in corrected and "天文" not in corrected
        assert gateway.calls[-1][1] is None
        await item_action(db, owner.id, item.id, base_revision=2, action="FORGET")
        await turn(owner, session, "请结合我的兴趣解释人工智能。")
        forgotten = json.dumps(gateway.calls[-1][0], ensure_ascii=False)
        assert "天文" not in forgotten and "生物" not in forgotten
        assert gateway.calls[-1][1] is None
        await item_action(db, owner.id, item.id, base_revision=3, action="RESTORE")
        await create_document(
            db,
            owner_user_id=owner.id,
            title="个人记忆.md",
            category="NOTE",
            content_markdown="喜欢图解",
            is_primary=True,
        )
        await settings_update(db, owner.id, 1, True, False)
        await turn(owner, session, "请结合我的兴趣解释人工智能。")
        disabled = json.dumps(gateway.calls[-1][0], ensure_ascii=False)
        assert "personal_context" not in gateway.calls[-1][0]
        assert "图解" not in disabled and "生物" not in disabled
        assert gateway.calls[-1][1] is None
        await turn(other, other_session, "请结合我的兴趣解释人工智能。")
        assert "personal_context" not in gateway.calls[-1][0]
        assert "天文" not in json.dumps(gateway.calls[-1][0], ensure_ascii=False)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_expiry_and_withdrawal_retire_runtime_scope_across_teachers(
    content_session,
    test_settings,
    monkeypatch,
):
    db = content_session
    owner = await student(test_settings)
    other = await student(test_settings, "scope.other")
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    session = await create_free_session(db, settings=settings, user=owner)
    other_session = await create_free_session(db, settings=settings, user=other)
    s = await saved_source(db, owner, session_id=session.id)
    result = with_summary(s)
    result.facts[0].valid_until = (utcnow() + timedelta(days=1)).isoformat()
    await apply_extraction(db, owner.id, result, [s])
    await db.commit()

    class Gateway:
        def continuation_scope(self, *_args, **_kwargs):
            return "synthetic-scope"

    async def context(target):
        return await build_runtime_context(
            db,
            settings=settings,
            gateway=Gateway(),
            session=target,
            operation=Operation.TEACH_TURN,
            query="我的兴趣",
        )

    first = await context(session)
    assert first.personal_items and not (await context(other_session)).personal_items
    session.stage = "JUNIOR"
    assert (await context(session)).personal_items == first.personal_items
    future = utcnow() + timedelta(days=2)
    monkeypatch.setattr("app.modules.memory.automatic.utcnow", lambda: future)
    monkeypatch.setattr("app.modules.ai.teaching_context.utcnow", lambda: future)
    expired = await context(session)
    assert not expired.personal_items and expired.continuation_scope != first.continuation_scope
    monkeypatch.undo()
    item = await db.scalar(select(PersonalMemoryItem))
    await item_action(db, owner.id, item.id, base_revision=1, action="FORGET")
    forgotten = await context(session)
    assert not forgotten.personal_items and forgotten.continuation_scope != first.continuation_scope
