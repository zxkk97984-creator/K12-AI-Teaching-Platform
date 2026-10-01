from __future__ import annotations

import base64
import json
import shutil
import uuid
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.main import create_app
from app.modules.content.importer import import_package
from app.modules.content.models import Chapter, ChapterRevision, ContentProfile, Course
from app.modules.content.package import load_package
from app.modules.content.schemas import ViewerScope
from app.modules.identity.models import LearnerProfile, UserRole
from app.modules.interactive.learning_bundle import ROOT, import_learning_activities, package_bytes
from app.modules.interactive.models import InteractiveFile, InteractiveRevision
from app.modules.interactive.package import build_document, read_package
from app.modules.learning.study_content import bind_interactive_scene
from app.modules.resources.models import Resource, ResourceChapterLink
from app.modules.resources.service import ResourceError, load_visible_resource
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers

COURSES = Path(__file__).resolve().parents[2] / "curriculum/source/imported/computing-ai-md-v1"


def test_four_offline_packages_are_reproducible_and_complete():
    items = json.loads((ROOT / "catalog.json").read_text())["items"]
    assert len(items) == 4
    for item in items:
        folder = ROOT / item["folder"]
        raw = package_bytes(folder)
        assert raw == package_bytes(folder)
        manifest = json.loads((folder / "manifest.json").read_text())
        files, parsed = read_package(
            raw, "lesson.zip", default={"stage": item["stage"], "purpose": manifest["purpose"]}
        )
        assert len(parsed.scenes) == len(parsed.prompts) == 4
        assert parsed.capabilities == ["SCENES", "CHECKPOINTS", "COMPLETION"]
        document = build_document(
            files,
            parsed,
            (Path(__file__).resolve().parents[1] / "app/modules/interactive/bridge.js").read_text(),
        )
        assert "connect-src 'none'" in document
        scripts = BeautifulSoup(document, "html.parser").select("script[src]")
        assert any(
            b"window.LESSON_SCENES" in base64.b64decode(script["src"].split(",", 1)[1])
            for script in scripts
        )


@pytest.mark.asyncio
async def test_four_stage_activities_restore_context_and_remain_private(
    test_settings, content_session, tmp_path
):
    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "resources")}
    )
    admin = await create_synthetic_user(
        settings,
        username="learning.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await import_package(content_session, load_package(COURSES), dry_run=False)
    first = await import_learning_activities(content_session, actor=admin, settings=settings)
    assert first["resources_created"] == first["versions_created"] == 4
    second = await import_learning_activities(content_session, actor=admin, settings=settings)
    assert second == {
        "resources_created": 0,
        "versions_created": 0,
        "versions_reused": 4,
        "files_restored": 0,
    }

    version = await content_session.scalar(select(InteractiveRevision))
    (Path(settings.resource_storage_root) / version.document_storage_key).unlink()
    recovered = await import_learning_activities(content_session, actor=admin, settings=settings)
    assert recovered["versions_created"] == 0 and recovered["files_restored"] == 1
    app = create_app(settings)
    stages = {"PRIMARY_LOWER": 2, "PRIMARY_UPPER": 5, "JUNIOR": 8, "SENIOR": 11}
    first_session = None
    for stage, grade in stages.items():
        user = await create_synthetic_user(
            settings,
            username=f"learning.{stage.lower()}",
            password="synthetic-pass-1",
            stage=stage,
            grade=grade,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
        ) as client:
            assert (await login(client, user.username, "synthetic-pass-1")).status_code == 200
            catalog = (await client.get("/api/v1/interactive/resources")).json()
            assert catalog["stage"] == stage and len(catalog["items"]) == 1
            item = catalog["items"][0]
            assert item["local_demo_visible"] and item["chapter_revision_ids"]
            learning_catalog = (
                await client.get("/api/v1/learning/catalog", params={"kind": "RESOURCE"})
            ).json()
            assert (
                next(row for row in learning_catalog["items"] if row["id"] == item["id"])[
                    "available"
                ]
                is True
            )
            started = await client.post(
                "/api/v1/interactive/sessions",
                json={"resource_id": item["id"]},
                headers=await csrf_headers(client),
            )
            assert started.status_code == 201, started.text
            session = started.json()
            document = (
                await client.get(f"/api/v1/interactive/sessions/{session['id']}/document")
            ).json()
            scene = document["manifest"]["scenes"][1]["id"]
            saved = await client.patch(
                f"/api/v1/interactive/sessions/{session['id']}/checkpoint",
                json={
                    "base_revision": session["base_revision"],
                    "event_id": str(uuid.uuid4()),
                    "scene_id": scene,
                    "game_state": {"step": 2},
                },
                headers=await csrf_headers(client),
            )
            assert saved.status_code == 200, saved.text
            restored = (await client.get(f"/api/v1/interactive/sessions/{session['id']}")).json()
            assert restored["session"]["game_state"] == {"step": 2}
            profile = await content_session.scalar(
                select(LearnerProfile).where(LearnerProfile.user_id == user.id)
            )
            bound = await bind_interactive_scene(
                content_session,
                scene={
                    "interactive_session_id": session["id"],
                    "content_id": item["id"],
                    "content_version": session["revision_id"],
                    "interactive_scene_id": scene,
                    "selected_text": "forged",
                },
                owner_id=user.id,
                profile=profile,
                settings=settings,
            )
            assert (
                "forged" not in bound["selected_text"] and item["title"] in bound["visible_section"]
            )
            assert '"step":2' in bound["selected_text"]
            assert "课件上报" in bound["selected_text"]
            if stage == "PRIMARY_LOWER":
                url = (
                    f"/api/v1/admin/resources/{item['id']}/interactive-revisions/"
                    f"{session['revision_id']}/clone"
                )
                denied = await client.post(url, json={}, headers=await csrf_headers(client))
                assert denied.status_code == 403
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
                ) as admin_client:
                    await login(admin_client, admin.username, "synthetic-pass-1")
                    assert (await admin_client.post(url, json={})).status_code == 403
                    copied = await admin_client.post(
                        url, json={}, headers=await csrf_headers(admin_client)
                    )
                    assert copied.status_code == 200, copied.text
                    draft = copied.json()
                    assert not draft["locked"] and draft["revision"] == 2
                    updated = draft["manifest"]
                    updated["prompts"][0]["text"] = "这是管理员修订后的第一段讲解。"
                    draft_url = (
                        f"/api/v1/admin/resources/{item['id']}/interactive-revisions/{draft['id']}"
                    )
                    edited = await admin_client.patch(
                        draft_url, json=updated, headers=await csrf_headers(admin_client)
                    )
                    assert edited.status_code == 200, edited.text
                    activated = await admin_client.post(
                        draft_url + "/activate", json={}, headers=await csrf_headers(admin_client)
                    )
                    assert activated.status_code == 200
                historical = (
                    await client.get(f"/api/v1/interactive/sessions/{session['id']}")
                ).json()
                assert historical["manifest"]["prompts"][0]["text"] != updated["prompts"][0]["text"]
            if first_session:
                assert (
                    await client.get(f"/api/v1/interactive/sessions/{first_session}")
                ).status_code == 404
            first_session = first_session or session["id"]
            resource = await content_session.get(Resource, uuid.UUID(item["id"]))
            with pytest.raises(ResourceError, match="不可用|不存在"):
                await load_visible_resource(
                    content_session,
                    viewer=ViewerScope(stage=stage, grade=grade, profile=ContentProfile.FORMAL),
                    resource_id=resource.id,
                )

    # Updated lecture revisions acquire links without replacing the old activity.
    updated_root = tmp_path / "updated-courses"
    shutil.copytree(COURSES, updated_root)
    course_path = updated_root / "courses/primary-ai/course.json"
    course = json.loads(course_path.read_text())
    spec = next(item for item in course["chapters"] if item["stable_slug"] == "ch-003-lower")
    body = json.loads((course_path.parent / spec["content_file"]).read_text())
    spec["revision"] = body["revision"] = 2
    body["blocks"][1]["text"] += "本次补充强调样例的代表性。"
    spec["content_file"] = "chapters/ch-003-lower-r2.json"
    (course_path.parent / spec["content_file"]).write_text(json.dumps(body, ensure_ascii=False))
    course_path.write_text(json.dumps(course, ensure_ascii=False))
    release = json.loads((updated_root / "release.json").read_text())
    release["release_key"] += "-rebind-test"
    (updated_root / "release.json").write_text(json.dumps(release))
    await import_package(content_session, load_package(updated_root), dry_run=False)
    assert (await import_learning_activities(content_session, actor=admin, settings=settings))[
        "versions_created"
    ] == 0
    resource = await content_session.scalar(
        select(Resource).where(Resource.stable_slug == "learning-ai-picture")
    )
    links = list(
        await content_session.scalars(
            select(ResourceChapterLink.chapter_revision_id).where(
                ResourceChapterLink.resource_id == resource.id
            )
        )
    )
    revisions = list(
        await content_session.scalars(
            select(ChapterRevision.revision)
            .join(Chapter)
            .join(Course)
            .where(
                Course.stable_slug == "primary-ai",
                Chapter.stable_slug == "ch-003-lower",
                ChapterRevision.id.in_(links),
            )
        )
    )
    assert sorted(revisions) == [1, 2]


@pytest.mark.asyncio
async def test_workspace_upgrade_preserves_edits_audio_and_locked_documents(
    test_settings, content_session, tmp_path
):
    import io
    import wave
    import zipfile

    from app.modules.interactive.learning_bundle import preserved_upgrade_package
    from app.modules.interactive.service import (
        activate_version,
        add_prompt_audio,
        clone_draft,
        update_draft,
    )

    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "resources")}
    )
    admin = await create_synthetic_user(
        settings,
        username="upgrade.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await import_package(content_session, load_package(COURSES), dry_run=False)
    await import_learning_activities(content_session, actor=admin, settings=settings)
    resource = await content_session.scalar(
        select(Resource).where(Resource.stable_slug == "learning-conditions-loops")
    )
    old = await content_session.get(InteractiveRevision, resource.active_interactive_revision_id)
    old_document = Path(settings.resource_storage_root, old.document_storage_key).read_bytes()
    draft = await clone_draft(
        content_session, resource_id=resource.id, revision_id=old.id, actor=admin, settings=settings
    )
    copied = draft["manifest"]
    copied["prompts"][0]["text"] = "这是保留的管理员台词，不要覆盖。"
    await update_draft(
        content_session,
        resource_id=resource.id,
        revision_id=uuid.UUID(draft["id"]),
        manifest_data=copied,
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\x00\x00" * 800)
    await add_prompt_audio(
        content_session,
        resource_id=resource.id,
        revision_id=uuid.UUID(draft["id"]),
        prompt_id=copied["prompts"][0]["id"],
        raw=output.getvalue(),
        filename="read.wav",
        settings=settings,
    )
    await activate_version(
        content_session,
        resource_id=resource.id,
        revision_id=uuid.UUID(draft["id"]),
        settings=settings,
    )
    new_root = tmp_path / "new-source"
    shutil.copytree(ROOT, new_root)
    with (new_root / "shared/style.css").open("a") as stream:
        stream.write("\n/* new workspace revision */\n")
    result = await import_learning_activities(
        content_session, actor=admin, settings=settings, root=new_root, upgrade_from=ROOT
    )
    assert result["versions_created"] == 4
    await content_session.refresh(resource)
    latest = await content_session.get(InteractiveRevision, resource.active_interactive_revision_id)
    assert latest.manifest["prompts"][0]["text"] == copied["prompts"][0]["text"]
    assert latest.manifest["prompts"][0]["audio"] == "audio/observe-read.wav"
    with zipfile.ZipFile(
        Path(settings.resource_storage_root, latest.package_storage_key)
    ) as archive:
        assert archive.read("audio/observe-read.wav") == output.getvalue()
    assert (
        old.locked_at
        and Path(settings.resource_storage_root, old.document_storage_key).read_bytes()
        == old_document
    )
    again = await import_learning_activities(
        content_session, actor=admin, settings=settings, root=new_root, upgrade_from=ROOT
    )
    assert again["versions_created"] == 0 and again["versions_reused"] == 4
    ordinary_setup = await import_learning_activities(
        content_session, actor=admin, settings=settings, root=new_root
    )
    assert ordinary_setup["versions_created"] == 0 and ordinary_setup["versions_reused"] == 4
    # An independently authored script is not a managed template.
    asset = await content_session.scalar(
        select(InteractiveFile).where(
            InteractiveFile.revision_id == latest.id,
            InteractiveFile.relative_path == "assets/activity.js",
        )
    )
    asset.sha256 = "f" * 64
    assert (
        await preserved_upgrade_package(
            content_session,
            active=latest,
            folder=new_root / "conditions-loops",
            previous_folder=ROOT / "conditions-loops",
            settings=settings,
        )
        is None
    )
