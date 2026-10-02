from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.main import create_app
from app.modules.identity.models import UserRole
from app.modules.interactive.example_bundle import ROOT, import_autoplay_examples, load_examples
from app.modules.interactive.models import InteractiveRevision
from app.modules.interactive.service import activate_version, clone_draft, update_draft
from app.modules.resources.models import Resource
from tests.identity_helpers import create_synthetic_user, login


def test_twelve_examples_parse_and_build():
    assert len(load_examples(ROOT)) == 12


@pytest.mark.asyncio
async def test_import_idempotency_stage_isolation_and_edited_version_preservation(
    test_settings, content_session, tmp_path
):
    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "resources")}
    )
    admin = await create_synthetic_user(
        settings,
        username="examples.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    result = await import_autoplay_examples(content_session, actor=admin, settings=settings)
    assert result["resources_created"] == result["versions_created"] == 12
    again = await import_autoplay_examples(content_session, actor=admin, settings=settings)
    assert again["resources_created"] == again["versions_created"] == 0
    assert again["versions_reused"] == 12
    app = create_app(settings)
    for stage, grade in [("PRIMARY_LOWER", 1), ("PRIMARY_UPPER", 4), ("JUNIOR", 7), ("SENIOR", 10)]:
        user = await create_synthetic_user(
            settings,
            username="examples." + stage.lower(),
            password="synthetic-pass-1",
            stage=stage,
            grade=grade,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
        ) as client:
            await login(client, user.username, "synthetic-pass-1")
            catalog = (await client.get("/api/v1/interactive/resources?purpose=LESSON")).json()
            assert catalog["stage"] == stage and len(catalog["items"]) == 3
    resource = await content_session.scalar(select(Resource))
    old_id = resource.active_interactive_revision_id
    draft = await clone_draft(
        content_session, resource_id=resource.id, revision_id=old_id, actor=admin, settings=settings
    )
    import uuid

    new_id = uuid.UUID(draft["id"])
    edited = draft["manifest"]
    edited["prompts"][0]["text"] = "管理员手动修订的讲解，重复导入应保留。"
    await update_draft(
        content_session, resource_id=resource.id, revision_id=new_id, manifest_data=edited
    )
    await activate_version(
        content_session, resource_id=resource.id, revision_id=new_id, settings=settings
    )
    preserved = await import_autoplay_examples(content_session, actor=admin, settings=settings)
    await content_session.refresh(resource)
    assert preserved["versions_skipped"] == 1 and resource.active_interactive_revision_id == new_id
    assert await content_session.get(InteractiveRevision, old_id) is not None
    version = await content_session.get(InteractiveRevision, new_id)
    assert version.manifest["prompts"][0]["text"] == edited["prompts"][0]["text"]
    assert Path(settings.resource_storage_root, version.document_storage_key).exists()
    # Leave the managed fixture active for subsequent browser seeding; the
    # edited historical version remains available and the preservation was checked above.
    await activate_version(
        content_session, resource_id=resource.id, revision_id=old_id, settings=settings
    )


@pytest.mark.asyncio
async def test_viewed_is_owner_scoped_idempotent_and_keeps_experiments_active(
    test_settings, content_session, tmp_path
):
    import uuid

    from sqlalchemy import func

    from app.modules.interactive.models import InteractiveEvent, InteractiveSession
    from tests.teaching_helpers import csrf_headers

    settings = test_settings.model_copy(update={"resource_storage_root": str(tmp_path / "viewed")})
    admin = await create_synthetic_user(
        settings,
        username="viewed.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await import_autoplay_examples(content_session, actor=admin, settings=settings)
    for name in ["viewed.child", "viewed.other"]:
        await create_synthetic_user(
            settings, username=name, password="synthetic-pass-1", stage="PRIMARY_UPPER", grade=4
        )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "viewed.child", "synthetic-pass-1")
        headers = await csrf_headers(client)
        items = (await client.get("/api/v1/interactive/resources?purpose=LESSON")).json()["items"]
        assert all(item["viewed_at"] is None for item in items)
        resource_id = str(
            await content_session.scalar(
                select(Resource.id).where(
                    Resource.stable_slug == "autoplay-primary-upper-cards-bubble-sort"
                )
            )
        )
        activity = (
            await client.post(
                "/api/v1/interactive/sessions", json={"resource_id": resource_id}, headers=headers
            )
        ).json()
        path = f"/api/v1/interactive/sessions/{activity['id']}"
        state = {
            "state_version": 1,
            "content_key": "autoplay-primary-upper-cards-bubble-sort",
            "practice": {"operated": True, "values": [9, 2, 7]},
        }
        first = await client.patch(
            path + "/checkpoint",
            json={
                "base_revision": 0,
                "event_id": "experiment-1",
                "game_state": state,
                "playback_step": 2,
            },
            headers=headers,
        )
        assert first.status_code == 200 and first.json()["host_state"] == {"playback_step": 2}
        body = {"base_revision": 1, "event_id": "view-ended-1"}
        viewed = await client.post(path + "/viewed", json=body, headers=headers)
        receipt = viewed.json()
        assert viewed.status_code == 200 and receipt["viewed_at"]
        assert (
            receipt["status"] == "ACTIVE"
            and receipt["completed_at"] is None
            and receipt["game_result"] is None
        )
        assert (await client.post(path + "/viewed", json=body, headers=headers)).json() == receipt
        assert (
            await client.post(path + "/viewed", json={**body, "base_revision": 2}, headers=headers)
        ).status_code == 409
        assert (
            await client.post(
                path + "/viewed",
                json={"base_revision": 1, "event_id": "stale-window"},
                headers=headers,
            )
        ).status_code == 409
        state["practice"]["values"] = [5, 1, 4]
        second = await client.patch(
            path + "/checkpoint",
            json={"base_revision": 2, "event_id": "experiment-2", "game_state": state},
            headers=headers,
        )
        assert second.status_code == 200 and second.json()["viewed_at"] == receipt["viewed_at"]
        again = await client.post(
            path + "/viewed",
            json={"base_revision": 3, "event_id": "watch-again-1"},
            headers=headers,
        )
        assert again.json()["viewed_at"] == receipt["viewed_at"]
        assert (
            await client.post(
                path + "/viewed", json={"base_revision": 4, "event_id": "no-csrf-123"}
            )
        ).status_code == 403
        malformed = {
            **state,
            "practice": {**state["practice"], "values": [1, 2, 100], "url": "javascript:alert(1)"},
        }
        bad = await client.patch(
            path + "/checkpoint",
            json={"base_revision": 4, "event_id": "bad-state-1", "game_state": malformed},
            headers=headers,
        )
        assert bad.status_code == 422
        detail = (await client.get(path)).json()["session"]
        assert detail["game_state"] == state and detail["base_revision"] == 4
        assert (await client.get("/api/v1/interactive/sessions")).json()["items"][0][
            "viewed_at"
        ] == receipt["viewed_at"]
        catalog = (await client.get("/api/v1/interactive/resources?purpose=LESSON")).json()["items"]
        assert (
            next(item for item in catalog if item["id"] == resource_id)["viewed_at"]
            == receipt["viewed_at"]
        )
        await login(client, "viewed.other", "synthetic-pass-1")
        assert (await client.get(path)).status_code == 404
        assert (
            await client.post(
                path + "/viewed",
                json={"base_revision": 4, "event_id": "wrong-owner-1"},
                headers=await csrf_headers(client),
            )
        ).status_code == 404
        other = (
            await client.post(
                "/api/v1/interactive/sessions",
                json={"resource_id": resource_id},
                headers=await csrf_headers(client),
            )
        ).json()
        assert other["game_state"] == {} and other["viewed_at"] is None
        await login(client, "viewed.child", "synthetic-pass-1")
        resumed = (
            await client.post(
                "/api/v1/interactive/sessions",
                json={"resource_id": resource_id},
                headers=await csrf_headers(client),
            )
        ).json()
        assert resumed["id"] == activity["id"] and resumed["game_state"] == state
    assert await content_session.scalar(select(func.count()).select_from(InteractiveSession)) == 2
    assert (
        await content_session.scalar(
            select(func.count())
            .select_from(InteractiveEvent)
            .where(InteractiveEvent.session_id == uuid.UUID(activity["id"]))
        )
        == 4
    )


def test_autoplay_state_accepts_only_bounded_inputs():
    from app.modules.interactive.autoplay_state import validate_state

    cases = {
        "primary-lower-input-process-output": {"input": "按键 B"},
        "primary-lower-sorting-by-rule": {"rule": "color"},
        "primary-lower-robot-instructions": {"route": "wrong"},
        "primary-upper-pixels-build-picture": {"size": 8},
        "primary-upper-cards-bubble-sort": {"values": [9, 2, 7]},
        "primary-upper-message-packets": {"order": "1,2,3"},
        "junior-linear-search": {"target": 99},
        "junior-stack-and-queue": {"kind": "queue", "items": ["B"], "removed": ["A"]},
        "junior-training-and-testing": {"testIndex": 1},
        "senior-shortest-path": {"start": "B", "end": "E"},
        "senior-gradient-descent": {"alpha": 0.6},
        "senior-classification-metrics": {"threshold": 0.7},
    }
    for key, practice in cases.items():
        state = {
            "state_version": 1,
            "content_key": "autoplay-" + key,
            "practice": {"operated": True, **practice},
        }
        validate_state(state, state["content_key"])
        for invalid in [
            {**state, "content_key": "another"},
            {**state, "state_version": 2},
            {**state, "practice": {**state["practice"], "html": "<script>"}},
        ]:
            with pytest.raises(ValueError):
                validate_state(invalid, state["content_key"])


@pytest.mark.asyncio
async def test_upgrade_keeps_old_sessions_and_skips_edited_prior_manifest(
    test_settings, content_session, tmp_path
):
    import io
    import json
    import uuid
    import zipfile

    from app.modules.content.models import ContentProfile
    from app.modules.content.schemas import ViewerScope
    from app.modules.interactive.models import InteractiveSession
    from app.modules.interactive.service import start_session

    old_root = tmp_path / "old-examples"
    (old_root / "packages").mkdir(parents=True)
    catalog = json.loads((ROOT / "catalog.json").read_text())
    (old_root / "catalog.json").write_text(json.dumps(catalog))
    # Legacy package format: same scenes, no account experiment capability.
    for item in catalog:
        target = old_root / item["package_zip"]
        with zipfile.ZipFile(ROOT / item["package_zip"]) as original:
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as old:
                for name in original.namelist():
                    data = original.read(name)
                    if name == "manifest.json":
                        manifest = json.loads(data)
                        manifest["capabilities"] = ["SCENES"]
                        data = json.dumps(manifest).encode()
                    old.writestr(name, data)
        target.write_bytes(output.getvalue())
    settings = test_settings.model_copy(update={"resource_storage_root": str(tmp_path / "upgrade")})
    admin = await create_synthetic_user(
        settings,
        username="upgrade.examples.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    learner = await create_synthetic_user(
        settings,
        username="upgrade.examples.child",
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    await import_autoplay_examples(content_session, actor=admin, settings=settings, root=old_root)
    rows = list(
        await content_session.scalars(
            select(Resource).where(Resource.stage == "PRIMARY_LOWER").order_by(Resource.stable_slug)
        )
    )
    resource, edited_resource = rows[:2]
    old_revision_id = resource.active_interactive_revision_id
    session = await start_session(
        content_session,
        resource_id=resource.id,
        owner_id=learner.id,
        viewer=ViewerScope(stage="PRIMARY_LOWER", grade=2, profile=ContentProfile.DEVELOPMENT),
        settings=settings,
    )
    draft = await clone_draft(
        content_session,
        resource_id=edited_resource.id,
        revision_id=edited_resource.active_interactive_revision_id,
        actor=admin,
        settings=settings,
    )
    manifest = draft["manifest"]
    manifest["prompts"][0]["text"] = "管理员编辑的旧包文字需要保留。"
    await update_draft(
        content_session,
        resource_id=edited_resource.id,
        revision_id=uuid.UUID(draft["id"]),
        manifest_data=manifest,
    )
    await activate_version(
        content_session,
        resource_id=edited_resource.id,
        revision_id=uuid.UUID(draft["id"]),
        settings=settings,
    )
    upgrade = await import_autoplay_examples(
        content_session, actor=admin, settings=settings, upgrade_from=old_root
    )
    assert upgrade["versions_created"] == 11 and upgrade["versions_skipped"] == 1
    saved = await content_session.get(InteractiveSession, uuid.UUID(session["id"]))
    assert (
        saved.revision_id == old_revision_id and saved.game_state == {} and saved.viewed_at is None
    )
    await content_session.refresh(resource)
    assert resource.active_interactive_revision_id != old_revision_id
    resumed = await start_session(
        content_session,
        resource_id=resource.id,
        owner_id=learner.id,
        viewer=ViewerScope(stage="PRIMARY_LOWER", grade=2, profile=ContentProfile.DEVELOPMENT),
        settings=settings,
    )
    assert resumed["revision_id"] == str(old_revision_id)
    restarted = await start_session(
        content_session,
        resource_id=resource.id,
        owner_id=learner.id,
        viewer=ViewerScope(stage="PRIMARY_LOWER", grade=2, profile=ContentProfile.DEVELOPMENT),
        settings=settings,
        restart=True,
    )
    assert restarted["revision_id"] == str(resource.active_interactive_revision_id)
    old_version = await content_session.get(InteractiveRevision, old_revision_id)
    assert "CHECKPOINTS" not in old_version.capabilities
    assert Path(settings.resource_storage_root, old_version.document_storage_key).exists()
    repeat = await import_autoplay_examples(
        content_session, actor=admin, settings=settings, upgrade_from=old_root
    )
    assert (
        repeat["versions_created"] == 0
        and repeat["versions_reused"] == 11
        and repeat["versions_skipped"] == 1
    )
