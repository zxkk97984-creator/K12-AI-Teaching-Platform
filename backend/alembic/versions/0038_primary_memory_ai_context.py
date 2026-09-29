"""Make the current personal Markdown note available to the account's Tutor."""

from __future__ import annotations

from alembic import op

revision = "0038_primary_memory_ai"
down_revision = "0037_interactive_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing primary notes were created with an opt-in flag disabled. This
    # one-time transition changes only that account's current primary note;
    # older revisions and separate notes retain their previous access state.
    # Bump the context revision so pending/replayed Tutor runs cannot reuse the
    # old no-memory request after the note becomes visible.
    op.execute(
        """
        WITH enabled AS (
          UPDATE memory_documents
          SET ai_enabled = TRUE
          WHERE is_primary AND NOT ai_enabled
          RETURNING owner_user_id
        )
        INSERT INTO memory_context_states (owner_user_id, revision, updated_at)
        SELECT DISTINCT owner_user_id, 1, now() FROM enabled
        ON CONFLICT (owner_user_id) DO UPDATE
        SET revision = memory_context_states.revision + 1,
            updated_at = now()
        """
    )
    op.create_check_constraint(
        "ck_memory_documents_primary_ai",
        "memory_documents",
        "NOT is_primary OR ai_enabled",
    )


def downgrade() -> None:
    op.drop_constraint("ck_memory_documents_primary_ai", "memory_documents", type_="check")
    # A downgrade never silently revokes an account's already enabled note.
