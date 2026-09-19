"""add the authoring closed loop: jobs, packages, artefacts, reviews, publications

Revision ID: 0012_authoring
Revises: 0011_resources
Create Date: 2026-09-19

T22. The database — not the service layer — enforces the two invariants that
matter:

* ``authoring_packages.status = 'HUMAN_APPROVED'`` requires a real human review
  row (``actor_kind = 'HUMAN_ADMIN'``) **and** at least one verified artefact.
  An AI/automation path therefore cannot self-approve, even if called directly.
* ``authoring_publications`` may only be inserted for an approved package with a
  verified artefact, and ``idempotency_key`` is unique so a repeated publish
  intent cannot create a second formal revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_authoring"
down_revision = "0011_resources"
branch_labels = None
depends_on = None

GUARD_APPROVAL = """
CREATE OR REPLACE FUNCTION authoring_guard_human_approval()
RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'HUMAN_APPROVED' THEN
        IF NOT EXISTS (
            SELECT 1 FROM authoring_reviews r
             WHERE r.package_id = NEW.id
               AND r.decision = 'APPROVED'
               AND r.actor_kind = 'HUMAN_ADMIN'
               AND r.package_revision = NEW.revision
        ) THEN
            RAISE EXCEPTION 'HUMAN_APPROVED requires a real human review row';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM authoring_artifacts a
             WHERE a.package_id = NEW.id AND a.verified_at IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'HUMAN_APPROVED requires at least one verified artefact';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

GUARD_PUBLICATION = """
CREATE OR REPLACE FUNCTION authoring_guard_publication()
RETURNS trigger AS $$
DECLARE
    package_status text;
    verified integer;
BEGIN
    SELECT p.status INTO package_status FROM authoring_packages p WHERE p.id = NEW.package_id;
    IF package_status IS NULL THEN
        RAISE EXCEPTION 'unknown authoring package %', NEW.package_id;
    END IF;
    IF package_status <> 'HUMAN_APPROVED' THEN
        RAISE EXCEPTION 'only a human approved package can be published';
    END IF;
    SELECT count(*) INTO verified FROM authoring_artifacts a
     WHERE a.package_id = NEW.package_id AND a.verified_at IS NOT NULL;
    IF verified = 0 THEN
        RAISE EXCEPTION 'publication requires a verified artefact';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "authoring_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "operation", sa.String(length=48), nullable=False, server_default="LESSON_PACKAGE_DRAFT"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("gateway_mode", sa.String(length=16), nullable=False),
        sa.Column("run_ref", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["identity_users.id"],
            name="fk_authoring_jobs_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chapter_revision_id"],
            ["content_chapter_revisions.id"],
            name="fk_authoring_jobs_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_authoring_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts",
            name="ck_authoring_jobs_budget",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_authoring_jobs_idempotency"),
    )
    op.create_index("ix_authoring_jobs_owner", "authoring_jobs", ["owner_user_id"])
    op.create_index("ix_authoring_jobs_revision", "authoring_jobs", ["chapter_revision_id"])
    op.create_index("ix_authoring_jobs_status", "authoring_jobs", ["status"])

    op.create_table(
        "authoring_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("asset_requests", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("published_revision", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["authoring_jobs.id"], name="fk_authoring_packages_job", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["chapter_revision_id"],
            ["content_chapter_revisions.id"],
            name="fk_authoring_packages_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'AUTO_VALIDATED', 'HUMAN_APPROVED', 'PUBLISHED', 'CANCELLED')",
            name="ck_authoring_packages_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_authoring_packages_revision"),
        sa.CheckConstraint(
            "jsonb_typeof(asset_requests) = 'array'",
            name="ck_authoring_packages_asset_requests_array",
        ),
    )
    op.create_index("ix_authoring_packages_job", "authoring_packages", ["job_id"])
    op.create_index("ix_authoring_packages_revision", "authoring_packages", ["chapter_revision_id"])
    op.create_index("ix_authoring_packages_status", "authoring_packages", ["status"])

    op.create_table(
        "authoring_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("detected_mime", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "rendered_by", sa.String(length=32), nullable=False, server_default="LOCAL_RENDERER"
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["authoring_packages.id"],
            name="fk_authoring_artifacts_package",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('LESSON_MARKDOWN', 'PACKAGE_MANIFEST')", name="ck_authoring_artifacts_kind"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_authoring_artifacts_size"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_authoring_artifacts_sha256"),
        sa.CheckConstraint(
            "storage_key !~ '\\.\\.' AND storage_key !~ '^/'",
            name="ck_authoring_artifacts_key_safe",
        ),
        sa.UniqueConstraint("package_id", "kind", name="uq_authoring_artifacts_package_kind"),
        sa.UniqueConstraint("storage_key", name="uq_authoring_artifacts_storage_key"),
    )
    op.create_index("ix_authoring_artifacts_package", "authoring_artifacts", ["package_id"])

    op.create_table(
        "authoring_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_kind", sa.String(length=16), nullable=False, server_default="HUMAN_ADMIN"),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("package_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["authoring_packages.id"],
            name="fk_authoring_reviews_package",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["identity_users.id"],
            name="fk_authoring_reviews_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("actor_kind IN ('HUMAN_ADMIN')", name="ck_authoring_reviews_actor_kind"),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')", name="ck_authoring_reviews_decision"
        ),
    )
    op.create_index("ix_authoring_reviews_package", "authoring_reviews", ["package_id"])

    op.create_table(
        "authoring_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("bundle_ref", sa.String(length=400), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["authoring_packages.id"],
            name="fk_authoring_publications_package",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            ["identity_users.id"],
            name="fk_authoring_publications_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chapter_revision_id"],
            ["content_chapter_revisions.id"],
            name="fk_authoring_publications_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_authoring_publications_revision"),
        sa.CheckConstraint(
            "artifact_sha256 ~ '^[0-9a-f]{64}$'", name="ck_authoring_publications_sha256"
        ),
        sa.UniqueConstraint(
            "package_id", "revision", name="uq_authoring_publications_package_revision"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_authoring_publications_idempotency"),
    )
    op.create_index("ix_authoring_publications_package", "authoring_publications", ["package_id"])

    op.execute(GUARD_APPROVAL)
    op.execute(
        "CREATE TRIGGER authoring_human_approval_guard "
        "BEFORE INSERT OR UPDATE ON authoring_packages "
        "FOR EACH ROW EXECUTE FUNCTION authoring_guard_human_approval();"
    )
    op.execute(GUARD_PUBLICATION)
    op.execute(
        "CREATE TRIGGER authoring_publication_guard "
        "BEFORE INSERT ON authoring_publications "
        "FOR EACH ROW EXECUTE FUNCTION authoring_guard_publication();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS authoring_publication_guard ON authoring_publications;")
    op.execute("DROP FUNCTION IF EXISTS authoring_guard_publication();")
    op.execute("DROP TRIGGER IF EXISTS authoring_human_approval_guard ON authoring_packages;")
    op.execute("DROP FUNCTION IF EXISTS authoring_guard_human_approval();")
    op.drop_index("ix_authoring_publications_package", table_name="authoring_publications")
    op.drop_table("authoring_publications")
    op.drop_index("ix_authoring_reviews_package", table_name="authoring_reviews")
    op.drop_table("authoring_reviews")
    op.drop_index("ix_authoring_artifacts_package", table_name="authoring_artifacts")
    op.drop_table("authoring_artifacts")
    op.drop_index("ix_authoring_packages_status", table_name="authoring_packages")
    op.drop_index("ix_authoring_packages_revision", table_name="authoring_packages")
    op.drop_index("ix_authoring_packages_job", table_name="authoring_packages")
    op.drop_table("authoring_packages")
    op.drop_index("ix_authoring_jobs_status", table_name="authoring_jobs")
    op.drop_index("ix_authoring_jobs_revision", table_name="authoring_jobs")
    op.drop_index("ix_authoring_jobs_owner", table_name="authoring_jobs")
    op.drop_table("authoring_jobs")
