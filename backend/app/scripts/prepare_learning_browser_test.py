"""Seed the isolated test database for the four-stage learning browser regression."""

import asyncio
import io
import json
import math
import os
import struct
import wave
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.core.test_database import validate_test_database_url
from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from app.modules.identity.models import LearnerProfile, PreferredStyle, UserRole, VoicePreference
from app.modules.identity.schemas import PreferencesPatch
from app.modules.identity.service import ensure_demo_user, update_preferences
from app.modules.interactive.example_bundle import import_autoplay_examples
from app.modules.interactive.learning_bundle import import_learning_activities
from app.modules.interactive.models import InteractiveRevision
from app.modules.interactive.service import activate_version, add_prompt_audio, clone_draft
from app.modules.resources.models import Resource

PASSWORD = "synthetic-html-pass-2026"


async def main():
    settings = Settings()
    if settings.app_env != "test" or settings.gateway_mode != "fixture":
        raise SystemExit("This browser seed requires APP_ENV=test and GATEWAY_MODE=fixture")
    validate_test_database_url(settings.active_database_url)
    engine = get_engine(settings.active_database_url, "test")
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            admin, _ = await ensure_demo_user(
                db,
                username="html.bundle.admin",
                password=PASSWORD,
                role=UserRole.ADMIN,
                stage=None,
                grade=None,
                preferred_style=PreferredStyle.AUTO,
                interests=[],
                settings=settings,
            )
            for stage, grade in [
                ("PRIMARY_LOWER", 2),
                ("PRIMARY_UPPER", 5),
                ("JUNIOR", 8),
                ("SENIOR", 11),
            ]:
                student, created = await ensure_demo_user(
                    db,
                    username="html." + stage.lower(),
                    password=PASSWORD,
                    role=UserRole.STUDENT,
                    stage=stage,
                    grade=grade,
                    preferred_style=PreferredStyle.AUTO,
                    interests=[],
                    settings=settings,
                )
                if created:
                    # These synthetic accounts exercise speech/media. Normal
                    # accounts keep their default and existing preferences.
                    profile = await db.get(LearnerProfile, student.id)
                    await update_preferences(
                        db,
                        student.id,
                        PreferencesPatch(
                            base_revision=profile.revision,
                            voice_preference=VoicePreference.INPUT_AND_OUTPUT,
                        ),
                    )
            if os.environ.get("K12_AUTOPLAY_EXAMPLES_E2E") == "1":
                previous_examples = os.environ.get("K12_AUTOPLAY_EXAMPLES_UPGRADE_FROM")
                print(
                    json.dumps(
                        await import_autoplay_examples(
                            db,
                            actor=admin,
                            settings=settings,
                            upgrade_from=Path(previous_examples) if previous_examples else None,
                        )
                    )
                )
                return
            root = (
                Path(__file__).resolve().parents[3]
                / "curriculum/source/imported/computing-ai-md-v1"
            )
            await import_package(db, load_package(root), dry_run=False)
            books = (
                Path(__file__).resolve().parents[3] / "curriculum/source/original/original-books-v1"
            )
            await import_package(db, load_package(books), dry_run=False)
            print(json.dumps(await import_learning_activities(db, actor=admin, settings=settings)))
            # A real, local media fixture exercises playback events, not speech quality.
            resource = await db.scalar(
                select(Resource).where(Resource.stable_slug == "learning-conditions-loops")
            )
            revision = await db.get(InteractiveRevision, resource.active_interactive_revision_id)
            if not revision.manifest["prompts"][0].get("audio"):
                import uuid

                draft = await clone_draft(
                    db,
                    resource_id=resource.id,
                    revision_id=revision.id,
                    actor=admin,
                    settings=settings,
                )
                output = io.BytesIO()
                with wave.open(output, "wb") as sound:
                    sound.setnchannels(1)
                    sound.setsampwidth(2)
                    sound.setframerate(8000)
                    sound.writeframes(
                        b"".join(
                            struct.pack("<h", int(300 * math.sin(2 * math.pi * 220 * i / 8000)))
                            for i in range(8000 * 6)
                        )
                    )
                await add_prompt_audio(
                    db,
                    resource_id=resource.id,
                    revision_id=uuid.UUID(draft["id"]),
                    prompt_id=draft["manifest"]["prompts"][0]["id"],
                    raw=output.getvalue(),
                    filename="event-test.wav",
                    settings=settings,
                )
                await activate_version(
                    db,
                    resource_id=resource.id,
                    revision_id=uuid.UUID(draft["id"]),
                    settings=settings,
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
