from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.core.test_database import validate_test_database_url
from app.main import create_app

TEST_DATABASE_URL = validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))
os.environ["APP_ENV"] = "test"
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        app_session_secret=os.environ["APP_SESSION_SECRET"],
        test_database_url=TEST_DATABASE_URL,
        database_url=TEST_DATABASE_URL,
        allowed_origins="http://127.0.0.1:15173",
        cookie_secure=False,
        login_rate_limit_attempts=5,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_test_db() -> Iterator[None]:
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["TEST_DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
    )
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_test_db(migrated_test_db: None, test_settings: Settings) -> AsyncIterator[None]:
    engine = get_engine(test_settings.active_database_url, "test")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE privacy_deletion_requests, codelab_task_favorites, "
                "codelab_task_catalog, codelab_code_runs, codelab_code_drafts, "
                "codelab_task_revisions, "
                "authoring_publications, authoring_reviews, "
                "authoring_artifacts, "
                "authoring_packages, authoring_jobs, "
                "resource_knowledge_points, resource_chapter_links, resource_variants, "
                "resource_items, "
                "recommendation_feedback_events, recommendation_feedback, "
                "recommendation_snapshots, "
                "learning_picturebook_progress, learning_open_events, learning_bookmarks, "
                "memory_document_versions, memory_documents, memory_context_states, "
                "memory_events, memory_candidates, learning_observations, "
                "learning_evidence_items, "
                "learning_quiz_evidence, assessment_quiz_review_links, "
                "assessment_quiz_hint_events, assessment_quiz_attempts, "
                "assessment_quiz_answer_drafts, "
                "assessment_quiz_questions, assessment_quiz_sessions, "
                "assessment_quiz_drafts, assessment_generation_jobs, "
                "assessment_designer_sessions, "
                "teaching_phase_events, learning_evidence, learning_policy_snapshots, "
                "teaching_remote_bindings, teaching_messages, teaching_agent_runs, "
                "teaching_lesson_sessions, content_reading_events, content_chapter_review_states, "
                "content_revision_knowledge_points, "
                "content_chapter_revisions, content_chapters, content_courses, "
                "content_knowledge_points, content_releases, login_attempts, auth_sessions, "
                "learner_profiles, identity_users RESTART IDENTITY CASCADE"
            )
        )
    yield
    await engine.dispose()


@pytest.fixture
def app(test_settings: Settings):
    return create_app(test_settings)


@pytest_asyncio.fixture
async def content_session(test_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:15173") as value:
        yield value
