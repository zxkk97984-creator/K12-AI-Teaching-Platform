from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from app.core.test_database import UnsafeTestDatabase, validate_test_database_url

BACKEND = Path(__file__).resolve().parents[1]


def _run_upgrade(url: str) -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["TEST_DATABASE_URL"] = url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
    )


def _clean_url(base_url: str, database: str) -> str:
    parsed = make_url(base_url)
    return parsed.set(database=database).render_as_string(hide_password=False)


@pytest.mark.asyncio
async def test_t04_baseline_upgrade_is_idempotent(test_settings):
    _run_upgrade(test_settings.active_database_url)
    _run_upgrade(test_settings.active_database_url)
    connection = await asyncpg.connect(
        test_settings.active_database_url.replace("postgresql+asyncpg", "postgresql")
    )
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        tables = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        constraints = await connection.fetch(
            "SELECT conname FROM pg_constraint WHERE contype = 'c' ORDER BY conname"
        )
        binding_columns = await connection.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'teaching_remote_bindings'"
        )
    finally:
        await connection.close()
    assert revision == "0017_knodo_remote_bindings"
    assert {"remote_scope", "remote_metadata"} <= {row["column_name"] for row in binding_columns}
    assert {
        "identity_users",
        "auth_sessions",
        "learner_profiles",
        "login_attempts",
        "content_courses",
        "content_chapters",
        "content_releases",
        "content_chapter_revisions",
        "content_knowledge_points",
        "content_revision_knowledge_points",
        "content_chapter_review_states",
        "content_reading_events",
        "teaching_lesson_sessions",
        "teaching_agent_runs",
        "teaching_messages",
        "teaching_remote_bindings",
        "learning_policy_snapshots",
        "assessment_designer_sessions",
        "assessment_generation_jobs",
        "assessment_quiz_drafts",
        "assessment_quiz_sessions",
        "assessment_quiz_questions",
        "assessment_quiz_attempts",
        "assessment_quiz_hint_events",
        "assessment_quiz_review_links",
        "learning_quiz_evidence",
        "learning_evidence",
        "teaching_phase_events",
        "learning_evidence_items",
        "learning_observations",
        "memory_candidates",
        "memory_events",
        "recommendation_snapshots",
        "recommendation_feedback",
        "recommendation_feedback_events",
        "resource_items",
        "resource_variants",
        "resource_chapter_links",
        "resource_knowledge_points",
        "authoring_jobs",
        "authoring_packages",
        "authoring_artifacts",
        "authoring_reviews",
        "authoring_publications",
        "codelab_task_revisions",
        "codelab_code_drafts",
        "codelab_code_runs",
        "privacy_deletion_requests",
    } <= {row["tablename"] for row in tables}
    constraint_names = {row["conname"] for row in constraints}
    assert {
        "ck_identity_users_username",
        "ck_auth_sessions_token_hash_sha256",
        "ck_learner_profiles_preferred_style",
        "ck_learner_profiles_voice_preference",
        "ck_learner_profiles_interests_array",
        "ck_teaching_runs_status",
        "ck_teaching_runs_attempt",
        "ck_teaching_sessions_stage",
        "ck_teaching_messages_role",
        "ck_teaching_bindings_kind",
        "ck_teaching_sessions_phase",
        "ck_teaching_sessions_lifecycle",
        "ck_assessment_job_status",
        "ck_assessment_draft_status",
        "ck_assessment_quiz_session_status",
        "ck_assessment_attempt_shape",
        "ck_assessment_hint_level",
        "ck_assessment_draft_human_requires_reviewer",
        "ck_learning_policy_evidence_level",
        "ck_learning_evidence_kind",
        "ck_learning_evidence_items_kind",
        "ck_learning_evidence_items_kps_array",
        "ck_learning_observations_level",
        "ck_learning_observations_revision",
        "ck_memory_candidates_status",
        "ck_memory_candidates_revision",
        "ck_memory_events_action",
        "ck_recommendation_snapshots_revision",
        "ck_recommendation_snapshots_primary",
        "ck_recommendation_feedback_state",
        "ck_resource_items_kind",
        "ck_resource_items_stage",
        "ck_resource_items_grade_range",
        "ck_resource_items_source_kind",
        "ck_resource_items_license",
        "ck_resource_items_review_status",
        "ck_resource_items_publication_status",
        "ck_resource_items_fixture_kind",
        "ck_resource_items_human_review_actor",
        "ck_resource_items_slug",
        "ck_resource_variants_variant",
        "ck_resource_variants_size",
        "ck_resource_variants_sha256",
        "ck_resource_variants_no_traversal",
        "ck_resource_variants_relative",
        "ck_resource_variants_no_backslash",
        "ck_recommendation_feedback_action",
        "ck_authoring_jobs_status",
        "ck_authoring_jobs_budget",
        "ck_authoring_packages_status",
        "ck_authoring_packages_revision",
        "ck_authoring_packages_asset_requests_array",
        "ck_authoring_artifacts_kind",
        "ck_authoring_artifacts_size",
        "ck_authoring_artifacts_sha256",
        "ck_authoring_artifacts_key_safe",
        "ck_authoring_reviews_actor_kind",
        "ck_authoring_reviews_decision",
        "ck_authoring_publications_revision",
        "ck_authoring_publications_sha256",
        "ck_codelab_task_revision_positive",
        "ck_codelab_task_status",
        "ck_codelab_task_review_status",
        "ck_codelab_task_io_contract_object",
        "ck_codelab_task_examples_array",
        "ck_codelab_task_manifest_object",
        "ck_codelab_task_binding_object",
        "ck_codelab_task_definition_sha256",
        "ck_codelab_draft_revision_positive",
        "ck_codelab_draft_code_sha256",
        "ck_codelab_run_revision_positive",
        "ck_codelab_run_code_sha256",
        "ck_codelab_run_status",
        "ck_codelab_run_execution_status",
        "ck_codelab_run_correctness_status",
        "ck_codelab_run_feedback_status",
        "ck_privacy_delete_status",
        "ck_privacy_delete_platform_status",
    } <= constraint_names


@pytest.mark.asyncio
async def test_clean_test_baseline_upgrade_is_idempotent(test_settings):
    admin_url = test_settings.active_database_url.replace("postgresql+asyncpg", "postgresql")
    connection = await asyncpg.connect(admin_url)
    clean_name = "k12r1_clean_test"
    exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", clean_name)
    if not exists:
        await connection.execute(f'CREATE DATABASE "{clean_name}"')
    await connection.close()
    clean_url = _clean_url(test_settings.active_database_url, clean_name)
    validate_test_database_url(clean_url)
    _run_upgrade(clean_url)
    _run_upgrade(clean_url)
    connection = await asyncpg.connect(clean_url.replace("postgresql+asyncpg", "postgresql"))
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        triggers = await connection.fetch(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgname"
        )
    finally:
        await connection.close()
    assert revision == "0017_knodo_remote_bindings"
    assert {
        "content_chapter_revisions_immutable",
        "content_review_state_guard",
        "resource_publication_guard_trigger",
        "authoring_human_approval_guard",
        "authoring_publication_guard",
        "codelab_task_revisions_immutable",
    } <= {row["tgname"] for row in triggers}


def test_development_database_is_rejected_before_migration(test_settings):
    dev_url = test_settings.active_database_url.replace(":55434/", ":55433/").replace(
        "k12r1_test", "k12r1_dev"
    )
    with pytest.raises(UnsafeTestDatabase):
        validate_test_database_url(dev_url)
