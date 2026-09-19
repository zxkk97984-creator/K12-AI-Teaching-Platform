"""tighten the authoring guards: all artefacts verified, republish allowed

Revision ID: 0013_authoring_guards
Revises: 0012_authoring
Create Date: 2026-09-19

T22 follow-up found while self-testing the closed loop:

* a package whose files were partly deleted could still be approved (the guard
  only asked for *one* verified artefact) — now **every** artefact must verify;
* re-publishing an already published package (a new formal revision) was
  rejected because the guard required the literal status ``HUMAN_APPROVED`` —
  ``PUBLISHED`` is the same approval, carried forward, so it is allowed too.

The revision of the package that carries the human review is still pinned by
``authoring_reviews.package_revision`` and re-checked on every approval.
"""

from __future__ import annotations

from alembic import op

revision = "0013_authoring_guards"
down_revision = "0012_authoring"
branch_labels = None
depends_on = None

GUARD_APPROVAL = """
CREATE OR REPLACE FUNCTION authoring_guard_human_approval()
RETURNS trigger AS $$
DECLARE
    artefacts integer;
    verified integer;
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
        SELECT count(*), count(*) FILTER (WHERE a.verified_at IS NOT NULL)
          INTO artefacts, verified
          FROM authoring_artifacts a
         WHERE a.package_id = NEW.id;
        IF artefacts = 0 THEN
            RAISE EXCEPTION 'HUMAN_APPROVED requires real rendered artefacts';
        END IF;
        IF verified <> artefacts THEN
            RAISE EXCEPTION 'HUMAN_APPROVED requires every artefact to verify';
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
    artefacts integer;
    verified integer;
BEGIN
    SELECT p.status INTO package_status FROM authoring_packages p WHERE p.id = NEW.package_id;
    IF package_status IS NULL THEN
        RAISE EXCEPTION 'unknown authoring package %', NEW.package_id;
    END IF;
    -- PUBLISHED carries the same human approval forward to a new revision.
    IF package_status NOT IN ('HUMAN_APPROVED', 'PUBLISHED') THEN
        RAISE EXCEPTION 'only a human approved package can be published';
    END IF;
    SELECT count(*), count(*) FILTER (WHERE a.verified_at IS NOT NULL)
      INTO artefacts, verified
      FROM authoring_artifacts a
     WHERE a.package_id = NEW.package_id;
    IF artefacts = 0 OR verified <> artefacts THEN
        RAISE EXCEPTION 'publication requires every artefact to verify';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_OLD_APPROVAL = """
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

_OLD_PUBLICATION = """
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
    op.execute(GUARD_APPROVAL)
    op.execute(GUARD_PUBLICATION)


def downgrade() -> None:
    op.execute(_OLD_APPROVAL)
    op.execute(_OLD_PUBLICATION)
