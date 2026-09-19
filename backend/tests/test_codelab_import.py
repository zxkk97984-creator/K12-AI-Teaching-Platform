from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.modules.codelab.importer import import_catalog
from app.modules.codelab.models import CodeTaskRevision


async def test_task_import_is_idempotent_and_keeps_tasks_draft(content_session) -> None:
    first = await import_catalog(content_session)
    second = await import_catalog(content_session)

    assert first.created == 3
    assert first.reused == 0
    assert second.created == 0
    assert second.reused == 3
    count = await content_session.scalar(select(func.count()).select_from(CodeTaskRevision))
    assert count == 3
    rows = (await content_session.scalars(select(CodeTaskRevision))).all()
    assert {(row.task_id, row.revision) for row in rows} == {
        ("temperature-converter", 1),
        ("list-summary", 1),
        ("binary-search", 1),
    }
    assert all(row.status == "DRAFT" and row.review_status == "UNREVIEWED" for row in rows)
    assert all(not hasattr(row, "reference_solution") for row in rows)


async def test_import_is_dry_run_without_persisting_rows(content_session) -> None:
    result = await import_catalog(content_session, dry_run=True)
    assert result.created == 3
    count = await content_session.scalar(select(func.count()).select_from(CodeTaskRevision))
    assert count == 0


async def test_imported_task_revision_cannot_be_overwritten(content_session) -> None:
    await import_catalog(content_session)
    with pytest.raises(Exception, match="immutable"):
        await content_session.execute(
            text(
                "UPDATE codelab_task_revisions SET title = 'changed' "
                "WHERE task_id = 'binary-search' AND revision = 1"
            )
        )
    await content_session.rollback()
