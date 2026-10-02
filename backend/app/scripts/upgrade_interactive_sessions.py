"""Explicit local migration of compatible active activities, retaining old records.

This is a one-time maintenance command, not an automatic latest-version policy.
Completed activities, events and immutable package revisions are never replaced.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.config import Settings
from app.core.database import get_engine
from app.modules.interactive.models import InteractiveFile, InteractiveRevision, InteractiveSession
from app.modules.resources.models import Resource
from app.modules.resources.service import store_for


def compatibility_issue(
    session: InteractiveSession,
    source: InteractiveRevision,
    target: InteractiveRevision,
    resource: Resource,
) -> str | None:
    if not resource.local_demo_visible or resource.interactive_purpose == "GAME":
        return "Only local teaching demos are supported"
    if source.manifest != target.manifest or source.capabilities != target.capabilities:
        return "Scenes, prompts or capabilities changed"
    if session.stage != resource.stage or source.resource_id != target.resource_id:
        return "Resource or learning stage changed"
    scene_ids = {scene["id"] for scene in target.manifest.get("scenes", [])}
    if session.current_scene_id is not None and session.current_scene_id not in scene_ids:
        return "Saved scene is missing"
    if session.host_state or session.game_result is not None or session.completed_at is not None:
        return "Additional saved state requires individual review"
    state = session.game_state
    if resource.stable_slug.startswith("autoplay-") and resource.interactive_purpose == "LESSON":
        return None if not state else "Autoplay lesson unexpectedly has saved practice state"
    if resource.stable_slug == "learning-conditions-loops":
        # The reviewed old/new restore functions use the same n/step representation.
        if not state:
            return None
        if (
            set(state) == {"n", "step"}
            and type(state["n"]) is int
            and type(state["step"]) is int
            and 1 <= state["n"] <= 20
            and 0 <= state["step"] <= state["n"]
        ):
            return None
        return "Loop parameters would be changed by restoration"
    if resource.stable_slug == "learning-binary-search" and not state:
        return None
    return "Saved state or renderer has not been reviewed for migration"


async def restoration_matches(db, source, target, store) -> bool:
    restorers = []
    for revision in (source, target):
        file = await db.scalar(
            select(InteractiveFile).where(
                InteractiveFile.revision_id == revision.id,
                InteractiveFile.relative_path == "assets/activity.js",
            )
        )
        if file is None or not store.exists(file.storage_key):
            return False
        code = store.resolve(file.storage_key).read_text(encoding="utf-8")
        match = re.search(r"restore:\s*(.*?)(?=\n\s*(?:reset|hint|render):)", code, re.S)
        if match is None:
            return False
        restorers.append(match.group(1).strip())
    return restorers[0] == restorers[1]


def write_private_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2, default=str)
        stream.flush()
        os.fsync(stream.fileno())


async def upgrade_sessions(
    db: AsyncSession, *, settings: Settings, apply: bool = False, backup: Path | None = None
) -> dict:
    if settings.app_env not in {"development", "test"}:
        raise ValueError("This command only supports development/test")
    if apply and backup is None:
        raise ValueError("A private backup path is required before migration")
    target = aliased(InteractiveRevision)
    statement = (
        select(InteractiveSession, InteractiveRevision, target, Resource)
        .join(InteractiveRevision, InteractiveSession.revision_id == InteractiveRevision.id)
        .join(Resource, InteractiveSession.resource_id == Resource.id)
        .join(target, Resource.active_interactive_revision_id == target.id)
        .where(
            InteractiveSession.status == "ACTIVE",
            InteractiveSession.revision_id != Resource.active_interactive_revision_id,
        )
        .order_by(InteractiveSession.id)
    )
    if apply:
        statement = statement.with_for_update(of=(InteractiveSession, Resource))
    rows = (await db.execute(statement)).all()
    eligible, skipped = [], []
    store = store_for(settings)
    for session, source, latest, resource in rows:
        issue = compatibility_issue(session, source, latest, resource)
        if (
            issue is None
            and resource.interactive_purpose == "EXPERIMENT"
            and not await restoration_matches(db, source, latest, store)
        ):
            issue = "Experiment restoration code changed or is missing"
        if issue is None and not store.exists(latest.document_storage_key):
            issue = "Latest document is missing"
        if issue:
            skipped.append({"resource": resource.stable_slug, "reason": issue})
        else:
            eligible.append((session, source, latest, resource, uuid.uuid4()))
    result = {
        "outdated_active": len(rows),
        "compatible": len(eligible),
        "upgraded": 0,
        "skipped": skipped,
    }
    if not apply or not eligible:
        await db.rollback()
        return result
    snapshot = {
        "created_at": datetime.now(UTC).isoformat(),
        "operation": "copy-active-progress-to-current-version",
        "activities": [
            {
                "original": {
                    column.key: getattr(session, column.key)
                    for column in InteractiveSession.__table__.columns
                },
                "new_session_id": str(new_id),
                "target_revision_id": str(latest.id),
                "from_version": source.revision,
                "to_version": latest.revision,
            }
            for session, source, latest, resource, new_id in eligible
        ],
    }
    write_private_snapshot(backup, snapshot)
    try:
        for session, *_ in eligible:
            session.status = "ABANDONED"
        # Flush the old active flags before inserting replacements, retaining
        # the database's one-active-activity-per-owner/resource constraint.
        await db.flush()
        for session, _source, latest, _resource, new_id in eligible:
            db.add(
                InteractiveSession(
                    id=new_id,
                    owner_user_id=session.owner_user_id,
                    resource_id=session.resource_id,
                    revision_id=latest.id,
                    stage=session.stage,
                    status="ACTIVE",
                    base_revision=session.base_revision,
                    current_scene_id=session.current_scene_id,
                    game_state=deepcopy(session.game_state),
                    host_state=deepcopy(session.host_state),
                )
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    result["upgraded"] = len(eligible)
    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Apply the compatible activity migration"
    )
    parser.add_argument(
        "--backup", type=Path, help="New private JSON snapshot outside the repository"
    )
    args = parser.parse_args()
    settings = Settings()
    engine = get_engine(settings.active_database_url, settings.app_env)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            print(
                json.dumps(
                    await upgrade_sessions(
                        db, settings=settings, apply=args.apply, backup=args.backup
                    ),
                    ensure_ascii=False,
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
