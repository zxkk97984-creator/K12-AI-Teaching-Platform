"""Small fail-closed checks for the server-owned continuation query."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.teaching.service import reusable_remote_conversation


class CapturingSession:
    def __init__(self, result: str | None):
        self.result = result
        self.statement = None

    async def scalar(self, statement):
        self.statement = statement
        return self.result


@pytest.mark.asyncio
async def test_reusable_binding_query_guards_owner_session_scope_kind_and_success() -> None:
    owner_id = uuid.uuid4()
    session_id = uuid.uuid4()
    run_id = uuid.uuid4()
    db = CapturingSession("conv-synthetic")
    run = SimpleNamespace(id=run_id, owner_user_id=owner_id, session_id=session_id)

    result = await reusable_remote_conversation(
        db,  # type: ignore[arg-type]
        run=run,  # type: ignore[arg-type]
        remote_scope="scope:tutor:v1",
    )

    assert result == "conv-synthetic"
    compiled = db.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"render_postcompile": True},
    )
    sql = str(compiled)
    values = set(compiled.params.values())
    assert "teaching_remote_bindings.owner_user_id" in sql
    assert "teaching_agent_runs.owner_user_id" in sql
    assert "teaching_agent_runs.session_id" in sql
    assert "teaching_remote_bindings.remote_scope" in sql
    assert "teaching_remote_bindings.remote_kind" in sql
    assert "teaching_agent_runs.status" in sql
    assert owner_id in values
    assert session_id in values
    assert run_id in values
    assert "scope:tutor:v1" in values
    assert "KNODO" in values
    assert "SUCCEEDED" in values
