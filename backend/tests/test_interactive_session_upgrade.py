import json
import stat
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.main import create_app
from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from app.modules.identity.models import User, UserRole
from app.modules.interactive.learning_bundle import import_learning_activities
from app.modules.interactive.models import InteractiveEvent, InteractiveSession
from app.modules.interactive.service import activate_version, clone_draft, update_draft
from app.modules.resources.models import Resource
from app.scripts.upgrade_interactive_sessions import upgrade_sessions
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers

COURSES = Path(__file__).resolve().parents[2] / "curriculum/source/imported/computing-ai-md-v1"


async def prepare(settings, db, tmp_path):
    settings = settings.model_copy(update={"resource_storage_root": str(tmp_path / "resources")})
    admin = await create_synthetic_user(
        settings,
        username="upgrade.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    learner = await create_synthetic_user(
        settings,
        username="upgrade.learner",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    await import_package(db, load_package(COURSES), dry_run=False)
    await import_learning_activities(db, actor=admin, settings=settings)
    resource = await db.scalar(
        select(Resource).where(Resource.stable_slug == "learning-conditions-loops")
    )
    source_id = resource.active_interactive_revision_id
    old = InteractiveSession(
        owner_user_id=learner.id,
        resource_id=resource.id,
        revision_id=source_id,
        stage="JUNIOR",
        current_scene_id="condition",
        base_revision=3,
        game_state={"n": 8, "step": 3},
        host_state={},
    )
    history = InteractiveSession(
        owner_user_id=learner.id,
        resource_id=resource.id,
        revision_id=source_id,
        stage="JUNIOR",
        status="COMPLETED",
        current_scene_id="reflect",
        game_state={"n": 8, "step": 8},
        game_result={"total": 20},
        completion_source="SDK_REPORTED",
        completed_at=datetime.now(UTC),
    )
    db.add_all([old, history])
    await db.flush()
    event = InteractiveEvent(
        session_id=old.id,
        owner_user_id=learner.id,
        client_event_id="prior-checkpoint",
        event_type="CHECKPOINT",
        request_hash="0" * 64,
        receipt={"revision_id": str(source_id)},
    )
    db.add(event)
    await db.commit()
    latest = await clone_draft(
        db, resource_id=resource.id, revision_id=source_id, actor=admin, settings=settings
    )
    latest_id = uuid.UUID(latest["id"])
    await activate_version(db, resource_id=resource.id, revision_id=latest_id, settings=settings)
    return settings, learner, resource.id, old.id, history.id, event.id, source_id, latest_id


@pytest.mark.asyncio
async def test_upgrade_preserves_progress_events_history_and_owner_scope(
    test_settings, content_session, tmp_path
):
    db = content_session
    (
        settings,
        learner,
        resource_id,
        old_id,
        history_id,
        event_id,
        source_id,
        latest_id,
    ) = await prepare(test_settings, db, tmp_path)
    audit = await upgrade_sessions(db, settings=settings)
    assert audit["compatible"] == 1 and audit["upgraded"] == 0
    assert (await db.get(InteractiveSession, old_id)).status == "ACTIVE"
    backup = tmp_path / "private" / "before.json"
    result = await upgrade_sessions(db, settings=settings, apply=True, backup=backup)
    assert result["upgraded"] == 1 and result["skipped"] == []
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    snapshot = json.loads(backup.read_text())
    assert snapshot["activities"][0]["original"]["game_state"] == {"n": 8, "step": 3}
    old = await db.get(InteractiveSession, old_id)
    await db.refresh(old)
    assert old.status == "ABANDONED" and old.revision_id == source_id
    assert old.current_scene_id == "condition" and old.game_state == {"n": 8, "step": 3}
    history = await db.get(InteractiveSession, history_id)
    assert history.status == "COMPLETED" and history.revision_id == source_id
    assert history.game_result == {"total": 20}
    assert (await db.get(InteractiveEvent, event_id)).receipt == {"revision_id": str(source_id)}
    assert await db.scalar(select(func.count()).select_from(InteractiveSession)) == 3
    assert await db.scalar(select(func.count()).select_from(InteractiveEvent)) == 1
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, learner.username, "synthetic-pass-1")
        resumed = await client.post(
            "/api/v1/interactive/sessions",
            json={"resource_id": str(resource_id)},
            headers=await csrf_headers(client),
        )
        assert resumed.status_code == 201
        current = resumed.json()
        assert current["revision_id"] == str(latest_id) and current["id"] != str(old_id)
        assert current["base_revision"] == 3
        assert current["current_scene_id"] == "condition" and current["game_state"] == {
            "n": 8,
            "step": 3,
        }
        assert (
            await client.get(f"/api/v1/interactive/sessions/{current['id']}/document")
        ).status_code == 200
        outsider = await create_synthetic_user(
            settings,
            username="upgrade.outsider",
            password="synthetic-pass-1",
            stage="JUNIOR",
            grade=8,
        )
        await login(client, outsider.username, "synthetic-pass-1")
        assert (
            await client.get(f"/api/v1/interactive/sessions/{current['id']}")
        ).status_code == 404
    again = await upgrade_sessions(
        db, settings=settings, apply=True, backup=tmp_path / "unused.json"
    )
    assert again["outdated_active"] == 0 and again["upgraded"] == 0
    assert not (tmp_path / "unused.json").exists()


@pytest.mark.asyncio
async def test_upgrade_rolls_back_atomically_and_skips_changed_lessons(
    test_settings, content_session, tmp_path, monkeypatch
):
    db = content_session
    (
        settings,
        learner,
        resource_id,
        old_id,
        history_id,
        event_id,
        source_id,
        latest_id,
    ) = await prepare(test_settings, db, tmp_path)
    with monkeypatch.context() as patch:

        async def fail_commit():
            raise RuntimeError("simulated commit failure")

        patch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            await upgrade_sessions(
                db, settings=settings, apply=True, backup=tmp_path / "failed.json"
            )
    assert (await db.get(InteractiveSession, old_id)).status == "ACTIVE"
    assert await db.scalar(select(func.count()).select_from(InteractiveSession)) == 2
    admin = await db.scalar(select(User).where(User.username == "upgrade.admin"))
    draft = await clone_draft(
        db, resource_id=resource_id, revision_id=latest_id, actor=admin, settings=settings
    )
    changed_id = uuid.UUID(draft["id"])
    changed = deepcopy(draft["manifest"])
    changed["prompts"][0]["text"] = "已修改的讲解，不自动迁移旧进度。"
    await update_draft(db, resource_id=resource_id, revision_id=changed_id, manifest_data=changed)
    await activate_version(db, resource_id=resource_id, revision_id=changed_id, settings=settings)
    result = await upgrade_sessions(
        db, settings=settings, apply=True, backup=tmp_path / "skipped.json"
    )
    assert result["upgraded"] == 0 and result["compatible"] == 0 and len(result["skipped"]) == 1
    assert (await db.get(InteractiveSession, old_id)).status == "ACTIVE"
    assert not (tmp_path / "skipped.json").exists()
