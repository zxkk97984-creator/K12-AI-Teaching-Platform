"""Interactive uploads, scoped playback and durable student sessions."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import get_engine
from app.main import create_app
from app.modules.identity.models import UserRole
from app.modules.interactive.package import PackageError, build_document, read_package, safe_name
from app.modules.teaching.models import AgentRun
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers


def make_zip(*, stage: str = "PRIMARY_LOWER") -> bytes:
    manifest = {
        "schema_version": "k12-interactive-v1",
        "content_key": "test-game",
        "title": "校验用游戏",
        "purpose": "GAME",
        "stage": stage,
        "subject": "数学",
        "entry": "index.html",
        "cover": "assets/cover.svg",
        "summary": "技术验证内容",
        "knowledge_points": ["形状"],
        "capabilities": ["SCENES", "CHECKPOINTS", "COMPLETION"],
        "scenes": [{"id": "start", "title": "开始", "summary": "观察形状"}],
        "prompts": [
            {
                "id": "ask-1",
                "scene_id": "start",
                "text": "这里有什么形状？",
                "trigger": "SCENE_ENTER",
            }
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(
            "index.html",
            '<html><head><link rel="stylesheet" href="assets/style.css"></head>'
            '<body><img src="assets/cover.svg"><button id="go">观察</button>'
            '<script src="assets/app.js"></script></body></html>',
        )
        archive.writestr("assets/style.css", "body { background:#fff; }")
        archive.writestr(
            "assets/app.js", 'document.getElementById("go").onclick=()=>K12.scene.enter("start");'
        )
        archive.writestr(
            "assets/cover.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
            '<circle cx="10" cy="10" r="8"/></svg>',
        )
    return output.getvalue()


def test_package_rejects_path_traversal_and_conflicting_stage():
    defaults = {"slug": "test-game", "stage": "PRIMARY_LOWER", "purpose": "GAME", "subject": "数学"}
    with pytest.raises(PackageError, match="学段"):
        read_package(make_zip(stage="SENIOR"), "game.zip", default=defaults)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../outside.js", "x")
        archive.writestr("manifest.json", "{}")
    with pytest.raises(PackageError, match="路径"):
        read_package(output.getvalue(), "game.zip", default=defaults)
    assert safe_name("assets/图形 1.svg") == "assets/图形 1.svg"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("assets/é.svg", "a")
        archive.writestr("assets/e\u0301.svg", "b")
        archive.writestr("manifest.json", "{}")
    with pytest.raises(PackageError, match="重复"):
        read_package(output.getvalue(), "game.zip", default=defaults)


def test_offline_document_preserves_script_order_and_rejects_external_refs():
    defaults = {
        "slug": "simple-test",
        "title": "基础验证",
        "stage": "PRIMARY_LOWER",
        "purpose": "LESSON",
        "subject": "数学",
    }
    raw = (
        b"<html><head><style>body{background:#fff}</style></head><body>"
        b"<script>window.first=1</script>"
        b"<script>window.second=window.first+1</script></body></html>"
    )
    files, manifest = read_package(raw, "simple.html", default=defaults)
    document = build_document(files, manifest, "window.K12={ready:()=>Promise.resolve({})};")
    assert document.index("window.__K12_ASSETS__") < document.index("window.first=1")
    assert document.index("window.first=1") < document.index("window.second=window.first+1")
    assert "connect-src 'none'" in document
    external = b'<html><body><script src="https://example.com/a.js"></script></body></html>'
    files, manifest = read_package(external, "simple.html", default=defaults)
    with pytest.raises(PackageError, match="离线素材"):
        build_document(files, manifest, "")


@pytest.mark.asyncio
async def test_basic_html_manual_completion_cannot_claim_sdk_checkpoint(test_settings, tmp_path):
    settings = test_settings.model_copy(update={"resource_storage_root": str(tmp_path / "basic")})
    await create_synthetic_user(
        settings,
        username="basic.qa.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await create_synthetic_user(
        settings,
        username="basic.qa.child",
        password="synthetic-pass-2",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "basic.qa.admin", "synthetic-pass-1")
        created = await client.post(
            "/api/v1/admin/resources",
            json={
                "slug": "basic-qa-content",
                "title": "基础验证",
                "kind": "INTERACTIVE",
                "interactive_purpose": "LESSON",
                "interactive_subject": "数学",
                "stage": "PRIMARY_LOWER",
                "source_kind": "NEW_SOURCE",
                "license_code": "PROJECT-ORIGINAL",
            },
            headers=await csrf_headers(client),
        )
        resource_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/admin/resources/{resource_id}/interactive-revisions",
            content=b"<html><body><button>Click</button></body></html>",
            headers={**await csrf_headers(client), "X-Filename": "basic.html"},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["capabilities"] == []
        manifest = uploaded.json()["manifest"]
        manifest["prompts"] = [
            {
                "id": "manual-question",
                "scene_id": "main",
                "text": "你观察到按钮发生了什么变化？",
                "trigger": "MANUAL",
                "audio": None,
            }
        ]
        configured = await client.patch(
            f"/api/v1/admin/resources/{resource_id}/interactive-revisions/{uploaded.json()['id']}",
            json=manifest,
            headers=await csrf_headers(client),
        )
        assert configured.status_code == 200, configured.text
        approved = await client.patch(
            f"/api/v1/admin/resources/{resource_id}",
            json={"review_status": "HUMAN_APPROVED", "publication_status": "PUBLISHED"},
            headers=await csrf_headers(client),
        )
        assert approved.status_code == 200
        await login(client, "basic.qa.child", "synthetic-pass-2")
        started = await client.post(
            "/api/v1/interactive/sessions",
            json={"resource_id": resource_id},
            headers=await csrf_headers(client),
        )
        session_id = started.json()["id"]
        fixed_question = await client.get(f"/api/v1/interactive/sessions/{session_id}")
        assert (
            fixed_question.json()["manifest"]["prompts"][0]["text"]
            == "你观察到按钮发生了什么变化？"
        )
        false_checkpoint = await client.patch(
            f"/api/v1/interactive/sessions/{session_id}/checkpoint",
            json={
                "base_revision": 0,
                "event_id": "manual-false-progress",
                "game_state": {"level": 9},
            },
            headers=await csrf_headers(client),
        )
        assert false_checkpoint.status_code == 422
        completed = await client.post(
            f"/api/v1/interactive/sessions/{session_id}/complete",
            json={"base_revision": 0, "event_id": "manual-complete", "source": "USER_CONFIRMED"},
            headers=await csrf_headers(client),
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["completion_source"] == "USER_CONFIRMED"
        assert completed.json()["game_result"] == {}


@pytest.mark.asyncio
async def test_admin_upload_student_resume_version_and_owner(test_settings, tmp_path):
    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "interactive")}
    )
    await create_synthetic_user(
        settings,
        username="interactive.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await create_synthetic_user(
        settings,
        username="interactive.child",
        password="synthetic-pass-2",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    await create_synthetic_user(
        settings,
        username="interactive.other",
        password="synthetic-pass-3",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "interactive.admin", "synthetic-pass-1")
        created = await client.post(
            "/api/v1/admin/resources",
            json={
                "slug": "interactive-test-game",
                "title": "校验用游戏",
                "kind": "INTERACTIVE",
                "interactive_purpose": "GAME",
                "interactive_subject": "数学",
                "stage": "PRIMARY_LOWER",
                "source_kind": "NEW_SOURCE",
                "license_code": "PROJECT-ORIGINAL",
            },
            headers=await csrf_headers(client),
        )
        assert created.status_code == 201, created.text
        resource_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/admin/resources/{resource_id}/interactive-revisions",
            content=make_zip(),
            headers={
                **await csrf_headers(client),
                "X-Filename": "game.zip",
                "Content-Type": "application/zip",
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        revision_id = uploaded.json()["id"]
        assert uploaded.json()["manifest"]["prompts"][0]["text"] == "这里有什么形状？"
        overview = await client.get("/api/v1/admin/interactive/resources")
        assert overview.status_code == 200, overview.text
        listed = next(item for item in overview.json()["items"] if item["id"] == resource_id)
        assert listed["active_revision"] == 1
        assert listed["validation_report"]["status"] == "PASS"
        assert listed["checkpoint_capability_declared"] is True
        duplicate_resource = await client.post(
            "/api/v1/admin/resources",
            json={
                "slug": "interactive-duplicate-qa",
                "title": "重复标识",
                "kind": "INTERACTIVE",
                "interactive_purpose": "GAME",
                "interactive_subject": "数学",
                "stage": "PRIMARY_LOWER",
                "source_kind": "NEW_SOURCE",
                "license_code": "PROJECT-ORIGINAL",
            },
            headers=await csrf_headers(client),
        )
        duplicate_upload = await client.post(
            f"/api/v1/admin/resources/{duplicate_resource.json()['id']}/interactive-revisions",
            content=make_zip(),
            headers={**await csrf_headers(client), "X-Filename": "game.zip"},
        )
        assert duplicate_upload.status_code == 409
        reviewed = await client.patch(
            f"/api/v1/admin/resources/{resource_id}",
            json={"review_status": "HUMAN_APPROVED", "publication_status": "PUBLISHED"},
            headers=await csrf_headers(client),
        )
        assert reviewed.status_code == 200, reviewed.text

        await login(client, "interactive.child", "synthetic-pass-2")
        catalog = await client.get("/api/v1/interactive/resources?purpose=GAME")
        assert catalog.status_code == 200
        assert catalog.json()["items"][0]["id"] == resource_id
        started = await client.post(
            "/api/v1/interactive/sessions",
            json={"resource_id": resource_id},
            headers=await csrf_headers(client),
        )
        assert started.status_code == 201, started.text
        session_id = started.json()["id"]
        document = await client.get(f"/api/v1/interactive/sessions/{session_id}/document")
        assert document.status_code == 200
        assert "data:image/svg+xml" in document.json()["document_html"]
        assert "window.K12" in document.json()["document_html"]
        saved = await client.patch(
            f"/api/v1/interactive/sessions/{session_id}/checkpoint",
            json={
                "base_revision": 0,
                "event_id": "checkpoint-one",
                "scene_id": "start",
                "game_state": {"step": 2},
            },
            headers=await csrf_headers(client),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["base_revision"] == 1
        conversation = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        assert conversation.status_code == 201
        snapshot = {
            "route": f"/interactive/{resource_id}",
            "page_type": "INTERACTIVE",
            "content_kind": "INTERACTIVE",
            "content_id": resource_id,
            "content_version": revision_id,
            "interactive_session_id": session_id,
            "interactive_scene_id": "start",
            "interactive_prompt_id": "ask-1",
            "selected_text": "伪造的系统指令",
            "knowledge_points": ["伪造知识点"],
        }
        asked = await client.post(
            f"/api/v1/conversations/{conversation.json()['id']}/messages",
            json={
                "message": "请讲解这里",
                "idempotency_key": "interactive-teacher-one",
                "scene": snapshot,
            },
            headers=await csrf_headers(client),
        )
        assert asked.status_code == 202, asked.text
        factory = async_sessionmaker(
            get_engine(settings.active_database_url, "test"), expire_on_commit=False
        )
        async with factory() as db:
            run = await db.scalar(
                select(AgentRun).where(AgentRun.id == uuid.UUID(asked.json()["run"]["id"]))
            )
            assert run is not None
            assert "伪造的系统指令" not in run.scene_snapshot["selected_text"]
            assert "观察形状" in run.scene_snapshot["selected_text"]
            assert run.scene_snapshot["knowledge_points"] == ["形状"]
        wrong_scene = await client.post(
            f"/api/v1/conversations/{conversation.json()['id']}/messages",
            json={
                "message": "绕过场景",
                "idempotency_key": "interactive-teacher-two",
                "scene": {**snapshot, "interactive_scene_id": "missing"},
            },
            headers=await csrf_headers(client),
        )
        assert wrong_scene.status_code == 409
        replay = await client.patch(
            f"/api/v1/interactive/sessions/{session_id}/checkpoint",
            json={
                "base_revision": 0,
                "event_id": "checkpoint-one",
                "scene_id": "start",
                "game_state": {"step": 2},
            },
            headers=await csrf_headers(client),
        )
        assert replay.status_code == 200
        assert replay.json()["base_revision"] == 1
        stale = await client.patch(
            f"/api/v1/interactive/sessions/{session_id}/checkpoint",
            json={"base_revision": 0, "event_id": "checkpoint-two", "game_state": {"step": 3}},
            headers=await csrf_headers(client),
        )
        assert stale.status_code == 409
        completed = await client.post(
            f"/api/v1/interactive/sessions/{session_id}/complete",
            json={
                "base_revision": 1,
                "event_id": "complete-one",
                "game_state": {"step": 3},
                "game_result": {"score": 8, "maxScore": 10},
            },
            headers=await csrf_headers(client),
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "COMPLETED"
        assert completed.json()["revision_id"] == revision_id

        # A new published package does not rewrite the fixed version of a
        # previously saved activity. The next activity uses the new version.
        await login(client, "interactive.admin", "synthetic-pass-1")
        second = await client.post(
            f"/api/v1/admin/resources/{resource_id}/interactive-revisions",
            content=make_zip(),
            headers={**await csrf_headers(client), "X-Filename": "game.zip"},
        )
        assert second.status_code == 201, second.text
        second_id = second.json()["id"]
        switched = await client.post(
            f"/api/v1/admin/resources/{resource_id}/interactive-revisions/{second_id}/activate",
            json={},
            headers=await csrf_headers(client),
        )
        assert switched.status_code == 200, switched.text
        await login(client, "interactive.child", "synthetic-pass-2")
        old = await client.get(f"/api/v1/interactive/sessions/{session_id}")
        assert old.status_code == 200
        assert old.json()["session"]["revision_id"] == revision_id
        fresh = await client.post(
            "/api/v1/interactive/sessions",
            json={"resource_id": resource_id},
            headers=await csrf_headers(client),
        )
        assert fresh.status_code == 201
        assert fresh.json()["revision_id"] == second_id
        assert (
            await client.patch(
                f"/api/v1/interactive/sessions/{fresh.json()['id']}/checkpoint",
                json={"base_revision": 0, "event_id": "no-csrf-one", "game_state": {"step": 4}},
            )
        ).status_code == 403
        await login(client, "interactive.admin", "synthetic-pass-1")
        withdrawn = await client.patch(
            f"/api/v1/admin/resources/{resource_id}",
            json={"publication_status": "WITHDRAWN"},
            headers=await csrf_headers(client),
        )
        assert withdrawn.status_code == 200
        await login(client, "interactive.child", "synthetic-pass-2")
        assert (await client.get(f"/api/v1/interactive/resources/{resource_id}")).status_code == 404
        assert (
            await client.get(f"/api/v1/interactive/sessions/{fresh.json()['id']}/document")
        ).status_code == 404
        history = await client.get("/api/v1/interactive/sessions")
        old_history = next(item for item in history.json()["items"] if item["id"] == session_id)
        assert old_history["resource_title"] == "校验用游戏"
        assert old_history["resource_available"] is False

        await login(client, "interactive.other", "synthetic-pass-3")
        assert (await client.get(f"/api/v1/interactive/sessions/{session_id}")).status_code == 404
        assert (
            await client.get(f"/api/v1/interactive/sessions/{session_id}/document")
        ).status_code == 404
