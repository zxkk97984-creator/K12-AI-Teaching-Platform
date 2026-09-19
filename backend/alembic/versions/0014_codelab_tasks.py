"""add immutable codelab task revisions and trusted contract metadata"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_codelab_tasks"
down_revision = "0013_authoring_guards"
branch_labels = None
depends_on = None

IMMUTABLE_TRIGGER = """
CREATE OR REPLACE FUNCTION codelab_task_revision_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'codelab task revisions are immutable; create a new revision';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "codelab_task_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("is_test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "review_status", sa.String(length=24), nullable=False, server_default="UNREVIEWED"
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=False),
        sa.Column("entrypoint", sa.String(length=64), nullable=False),
        sa.Column("io_contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("test_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chapter_binding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("definition_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="ck_codelab_task_revision_positive"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_codelab_task_status"
        ),
        sa.CheckConstraint(
            "review_status IN ('UNREVIEWED', 'HUMAN_REVIEWED')",
            name="ck_codelab_task_review_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(io_contract) = 'object'", name="ck_codelab_task_io_contract_object"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(examples) = 'array'", name="ck_codelab_task_examples_array"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(test_manifest) = 'object'",
            name="ck_codelab_task_manifest_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(chapter_binding) = 'object'",
            name="ck_codelab_task_binding_object",
        ),
        sa.CheckConstraint(
            "definition_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_task_definition_sha256"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "revision", name="uq_codelab_task_revision"),
    )
    op.create_index(
        "ix_codelab_task_revisions_status", "codelab_task_revisions", ["status"], unique=False
    )
    op.execute(IMMUTABLE_TRIGGER)
    op.execute(
        """
        CREATE TRIGGER codelab_task_revisions_immutable
        BEFORE UPDATE OR DELETE ON codelab_task_revisions
        FOR EACH ROW EXECUTE FUNCTION codelab_task_revision_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS codelab_task_revisions_immutable ON codelab_task_revisions")
    op.execute("DROP FUNCTION IF EXISTS codelab_task_revision_immutable()")
    op.drop_index("ix_codelab_task_revisions_status", table_name="codelab_task_revisions")
    op.drop_table("codelab_task_revisions")
