"""add versioned curriculum content library

Revision ID: 0003_content_library
Revises: 0002_identity_constraints
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_content_library"
down_revision = "0002_identity_constraints"
branch_labels = None
depends_on = None

SHA256_REGEX = "^[0-9a-f]{64}$"
SLUG_REGEX = "^[a-z0-9]+(-[a-z0-9]+)*$"

GRADE_RANGE_SQL = (
    "(grade_min IS NULL AND grade_max IS NULL) OR "
    "(grade_min IS NOT NULL AND grade_max IS NOT NULL AND grade_min <= grade_max "
    "AND grade_min >= CASE stage "
    "WHEN 'PRIMARY_LOWER' THEN 1 WHEN 'PRIMARY_UPPER' THEN 4 "
    "WHEN 'JUNIOR' THEN 7 ELSE 10 END "
    "AND grade_max <= CASE stage "
    "WHEN 'PRIMARY_LOWER' THEN 3 WHEN 'PRIMARY_UPPER' THEN 6 "
    "WHEN 'JUNIOR' THEN 9 ELSE 12 END)"
)

IMMUTABLE_REVISION_FUNCTION = """
CREATE OR REPLACE FUNCTION content_chapter_revisions_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'content_chapter_revisions rows are immutable; create a new revision';
END;
$$ LANGUAGE plpgsql;
"""

GUARD_PUBLICATION_FUNCTION = """
CREATE OR REPLACE FUNCTION content_review_state_guard()
RETURNS trigger AS $$
DECLARE
    fixture boolean;
    license text;
BEGIN
    IF NEW.publication_status = 'PUBLISHED' THEN
        SELECT r.is_test_fixture, rev.license_code
          INTO fixture, license
          FROM content_chapter_revisions rev
          JOIN content_releases r ON r.id = rev.release_id
         WHERE rev.id = NEW.revision_id;
        IF fixture IS NULL THEN
            RAISE EXCEPTION 'unknown chapter revision %', NEW.revision_id;
        END IF;
        IF fixture OR license = 'SYNTHETIC-FIXTURE' THEN
            RAISE EXCEPTION 'synthetic fixture content cannot be published';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "content_courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("stable_slug", name="uq_content_courses_slug"),
        sa.CheckConstraint(f"stable_slug ~ '{SLUG_REGEX}'", name="ck_content_courses_slug"),
    )
    op.create_index("ix_content_courses_stable_slug", "content_courses", ["stable_slug"])

    op.create_table(
        "content_chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_courses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stable_slug", sa.String(length=120), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("course_id", "stable_slug", name="uq_content_chapters_course_slug"),
        sa.CheckConstraint(f"stable_slug ~ '{SLUG_REGEX}'", name="ck_content_chapters_slug"),
        sa.CheckConstraint("order_index >= 0", name="ck_content_chapters_order"),
    )
    op.create_index("ix_content_chapters_course_id", "content_chapters", ["course_id"])

    op.create_table(
        "content_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_key", sa.String(length=160), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("is_test_fixture", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("release_key", name="uq_content_releases_key"),
        sa.CheckConstraint(
            "source_kind IN ('LEGACY_REUSED', 'NEW_SOURCE', 'SYNTHETIC_FIXTURE')",
            name="ck_content_releases_source_kind",
        ),
        sa.CheckConstraint(
            "(source_kind = 'SYNTHETIC_FIXTURE') = is_test_fixture",
            name="ck_content_releases_fixture_kind",
        ),
        sa.CheckConstraint(
            f"manifest_hash ~ '{SHA256_REGEX}'", name="ck_content_releases_manifest_hash"
        ),
    )
    op.create_index("ix_content_releases_release_key", "content_releases", ["release_key"])

    op.create_table(
        "content_chapter_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "release_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_releases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("grade_min", sa.Integer(), nullable=True),
        sa.Column("grade_max", sa.Integer(), nullable=True),
        sa.Column("objectives", postgresql.JSONB(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("license_code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("chapter_id", "revision", name="uq_content_revisions_chapter_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_content_revisions_number"),
        sa.CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_content_revisions_stage",
        ),
        sa.CheckConstraint(GRADE_RANGE_SQL, name="ck_content_revisions_grade_range"),
        sa.CheckConstraint("jsonb_typeof(body) = 'array'", name="ck_content_revisions_body_array"),
        sa.CheckConstraint(
            "jsonb_array_length(body) BETWEEN 1 AND 400",
            name="ck_content_revisions_body_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(objectives) = 'array'",
            name="ck_content_revisions_objectives_array",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(objectives) BETWEEN 1 AND 8",
            name="ck_content_revisions_objectives_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_manifest) = 'object'",
            name="ck_content_revisions_source_manifest_object",
        ),
        sa.CheckConstraint(
            f"content_hash ~ '{SHA256_REGEX}'", name="ck_content_revisions_content_hash"
        ),
        sa.CheckConstraint(
            "license_code IN ('CC-BY', 'CC-BY-SA', 'CC0', 'PROJECT-ORIGINAL', "
            "'SYNTHETIC-FIXTURE', 'UNKNOWN')",
            name="ck_content_revisions_license",
        ),
    )
    op.create_index(
        "ix_content_chapter_revisions_release_id", "content_chapter_revisions", ["release_id"]
    )
    op.create_index(
        "ix_content_chapter_revisions_chapter_id", "content_chapter_revisions", ["chapter_id"]
    )

    op.create_table(
        "content_knowledge_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("stable_slug", name="uq_content_knowledge_points_slug"),
        sa.CheckConstraint(
            f"stable_slug ~ '{SLUG_REGEX}'", name="ck_content_knowledge_points_slug"
        ),
    )
    op.create_index("ix_content_knowledge_points_slug", "content_knowledge_points", ["stable_slug"])

    op.create_table(
        "content_revision_knowledge_points",
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "knowledge_point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_knowledge_points.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("revision_id", "position", name="uq_content_revision_kp_position"),
        sa.CheckConstraint("position >= 0", name="ck_content_revision_kp_position"),
    )

    op.create_table(
        "content_chapter_review_states",
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "review_status", sa.String(length=24), nullable=False, server_default="UNREVIEWED"
        ),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "publication_status",
            sa.String(length=16),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("published_by", sa.String(length=160), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(length=160), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "review_status IN ('UNREVIEWED', 'AUTO_VALIDATED', 'HUMAN_APPROVED')",
            name="ck_content_review_status",
        ),
        sa.CheckConstraint(
            "publication_status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_content_publication_status",
        ),
        sa.CheckConstraint(
            "(review_status = 'HUMAN_APPROVED') = "
            "(reviewer IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_content_review_human_evidence",
        ),
        sa.CheckConstraint(
            "review_status <> 'AUTO_VALIDATED' OR (reviewer IS NULL AND reviewed_at IS NULL)",
            name="ck_content_review_auto_has_no_reviewer",
        ),
        sa.CheckConstraint(
            "publication_status <> 'PUBLISHED' OR "
            "(review_status = 'HUMAN_APPROVED' AND published_by IS NOT NULL "
            "AND published_at IS NOT NULL)",
            name="ck_content_published_requires_approval",
        ),
        sa.CheckConstraint(
            "(publication_status = 'WITHDRAWN') = "
            "(withdrawn_by IS NOT NULL AND withdrawn_at IS NOT NULL)",
            name="ck_content_withdrawn_evidence",
        ),
    )

    op.execute(IMMUTABLE_REVISION_FUNCTION)
    op.execute(
        "CREATE TRIGGER content_chapter_revisions_immutable "
        "BEFORE UPDATE OR DELETE ON content_chapter_revisions "
        "FOR EACH ROW EXECUTE FUNCTION content_chapter_revisions_immutable();"
    )
    op.execute(GUARD_PUBLICATION_FUNCTION)
    op.execute(
        "CREATE TRIGGER content_review_state_guard "
        "BEFORE INSERT OR UPDATE ON content_chapter_review_states "
        "FOR EACH ROW EXECUTE FUNCTION content_review_state_guard();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS content_review_state_guard ON content_chapter_review_states")
    op.execute(
        "DROP TRIGGER IF EXISTS content_chapter_revisions_immutable ON content_chapter_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS content_review_state_guard()")
    op.execute("DROP FUNCTION IF EXISTS content_chapter_revisions_immutable()")
    op.drop_table("content_chapter_review_states")
    op.drop_table("content_revision_knowledge_points")
    op.drop_index("ix_content_knowledge_points_slug", table_name="content_knowledge_points")
    op.drop_table("content_knowledge_points")
    op.drop_index("ix_content_chapter_revisions_chapter_id", table_name="content_chapter_revisions")
    op.drop_index("ix_content_chapter_revisions_release_id", table_name="content_chapter_revisions")
    op.drop_table("content_chapter_revisions")
    op.drop_index("ix_content_releases_release_key", table_name="content_releases")
    op.drop_table("content_releases")
    op.drop_index("ix_content_chapters_course_id", table_name="content_chapters")
    op.drop_table("content_chapters")
    op.drop_index("ix_content_courses_stable_slug", table_name="content_courses")
    op.drop_table("content_courses")
