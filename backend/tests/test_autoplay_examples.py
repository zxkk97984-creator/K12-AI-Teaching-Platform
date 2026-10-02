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
