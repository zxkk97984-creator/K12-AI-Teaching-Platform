"""add learning resource registry, variants and curriculum bindings

Revision ID: 0011_resources
Revises: 0010_recommendation
Create Date: 2026-09-19

T20: registered Word/PPT/video resources with a real student entry.

* ``resource_items`` — metadata: stage/grade, provenance, licence, review,
  publication and fixture marker. Reuses the content vocabulary so a resource
  cannot claim a review state the curriculum does not have.
* ``resource_variants`` — the stored files. ``SOURCE`` (original) and
  ``PREVIEW`` (derived) are different rows; the short-lived download ticket is
  never a row.
* ``resource_chapter_links`` — binds a resource to an immutable chapter
  revision, the same unit the T06 release query uses.
* ``resource_knowledge_points`` — knowledge point coverage.
* A trigger refuses to publish any synthetic fixture resource.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_resources"
down_revision = "0010_recommendation"
branch_labels = None
depends_on = None

GUARD_PUBLICATION_FUNCTION = """
CREATE OR REPLACE FUNCTION resource_publication_guard()
RETURNS trigger AS $$
BEGIN
    IF NEW.publication_status = 'PUBLISHED' THEN
        IF NEW.is_test_fixture OR NEW.source_kind = 'SYNTHETIC_FIXTURE' THEN
            RAISE EXCEPTION 'synthetic fixture resources cannot be published';
        END IF;
        IF NEW.license_code = 'SYNTHETIC-FIXTURE' THEN
            RAISE EXCEPTION 'synthetic fixture licence cannot be published';
        END IF;
    END IF;
    IF NEW.review_status = 'HUMAN_APPROVED'
       AND (NEW.reviewer_id IS NULL OR NEW.reviewed_at IS NULL) THEN
        RAISE EXCEPTION 'human approval requires a reviewer and timestamp';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "resource_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("grade_min", sa.Integer(), nullable=True),
        sa.Column("grade_max", sa.Integer(), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("license_code", sa.String(length=32), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "review_status", sa.String(length=16), nullable=False, server_default="UNREVIEWED"
        ),
        sa.Column(
            "publication_status", sa.String(length=16), nullable=False, server_default="DRAFT"
        ),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["identity_users.id"],
            name="fk_resource_items_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["identity_users.id"],
            name="fk_resource_items_uploader",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('WORD', 'SLIDES', 'VIDEO', 'PDF', 'IMAGE')", name="ck_resource_items_kind"
        ),
        sa.CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_resource_items_stage",
        ),
        sa.CheckConstraint(
            "(grade_min IS NULL AND grade_max IS NULL) OR "
            "(grade_min IS NOT NULL AND grade_max IS NOT NULL AND grade_min <= grade_max "
            "AND grade_min >= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 1 WHEN 'PRIMARY_UPPER' THEN 4 "
            "WHEN 'JUNIOR' THEN 7 ELSE 10 END "
            "AND grade_max <= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 3 WHEN 'PRIMARY_UPPER' THEN 6 "
            "WHEN 'JUNIOR' THEN 9 ELSE 12 END)",
            name="ck_resource_items_grade_range",
        ),
        sa.CheckConstraint(
            "source_kind IN ('LEGACY_REUSED', 'NEW_SOURCE', 'SYNTHETIC_FIXTURE')",
            name="ck_resource_items_source_kind",
        ),
        sa.CheckConstraint(
            "license_code IN ('CC-BY', 'CC-BY-SA', 'CC0', 'PROJECT-ORIGINAL', "
            "'SYNTHETIC-FIXTURE', 'UNKNOWN')",
            name="ck_resource_items_license",
        ),
        sa.CheckConstraint(
            "review_status IN ('UNREVIEWED', 'AUTO_VALIDATED', 'HUMAN_APPROVED')",
            name="ck_resource_items_review_status",
        ),
        sa.CheckConstraint(
            "publication_status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_resource_items_publication_status",
        ),
        sa.CheckConstraint(
            "(source_kind = 'SYNTHETIC_FIXTURE') = is_test_fixture",
            name="ck_resource_items_fixture_kind",
        ),
        sa.CheckConstraint(
            "(review_status <> 'HUMAN_APPROVED') OR "
            "(reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_resource_items_human_review_actor",
        ),
        sa.CheckConstraint(
            "stable_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_resource_items_slug"
        ),
        sa.UniqueConstraint("stable_slug", name="uq_resource_items_slug"),
    )
    op.create_index("ix_resource_items_stage", "resource_items", ["stage"])
    op.create_index("ix_resource_items_uploader", "resource_items", ["uploaded_by_user_id"])

    op.create_table(
        "resource_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("declared_mime", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("detected_mime", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resource_items.id"],
            name="fk_resource_variants_resource",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("variant IN ('SOURCE', 'PREVIEW')", name="ck_resource_variants_variant"),
        sa.CheckConstraint("size_bytes > 0", name="ck_resource_variants_size"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_resource_variants_sha256"),
        sa.CheckConstraint("storage_key !~ '\\.\\.'", name="ck_resource_variants_no_traversal"),
        sa.CheckConstraint("storage_key !~ '^/'", name="ck_resource_variants_relative"),
        sa.CheckConstraint("storage_key !~ '\\\\'", name="ck_resource_variants_no_backslash"),
        sa.UniqueConstraint("resource_id", "variant", name="uq_resource_variants_resource_variant"),
        sa.UniqueConstraint("storage_key", name="uq_resource_variants_storage_key"),
    )
    op.create_index("ix_resource_variants_resource", "resource_variants", ["resource_id"])

    op.create_table(
        "resource_chapter_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resource_items.id"],
            name="fk_resource_chapter_links_resource",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chapter_revision_id"],
            ["content_chapter_revisions.id"],
            name="fk_resource_chapter_links_revision",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "resource_id", "chapter_revision_id", name="uq_resource_chapter_links_pair"
        ),
    )
    op.create_index(
        "ix_resource_chapter_links_revision", "resource_chapter_links", ["chapter_revision_id"]
    )
    op.create_index("ix_resource_chapter_links_resource", "resource_chapter_links", ["resource_id"])

    op.create_table(
        "resource_knowledge_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resource_items.id"],
            name="fk_resource_kp_resource",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["content_knowledge_points.id"],
            name="fk_resource_kp_knowledge_point",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "resource_id", "knowledge_point_id", name="uq_resource_knowledge_points_pair"
        ),
    )
    op.create_index(
        "ix_resource_knowledge_points_kp", "resource_knowledge_points", ["knowledge_point_id"]
    )

    op.execute(GUARD_PUBLICATION_FUNCTION)
    op.execute(
        "CREATE TRIGGER resource_publication_guard_trigger "
        "BEFORE INSERT OR UPDATE ON resource_items "
        "FOR EACH ROW EXECUTE FUNCTION resource_publication_guard();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS resource_publication_guard_trigger ON resource_items;")
    op.execute("DROP FUNCTION IF EXISTS resource_publication_guard();")
    op.drop_index("ix_resource_knowledge_points_kp", table_name="resource_knowledge_points")
    op.drop_table("resource_knowledge_points")
    op.drop_index("ix_resource_chapter_links_resource", table_name="resource_chapter_links")
    op.drop_index("ix_resource_chapter_links_revision", table_name="resource_chapter_links")
    op.drop_table("resource_chapter_links")
    op.drop_index("ix_resource_variants_resource", table_name="resource_variants")
    op.drop_table("resource_variants")
    op.drop_index("ix_resource_items_uploader", table_name="resource_items")
    op.drop_index("ix_resource_items_stage", table_name="resource_items")
    op.drop_table("resource_items")
