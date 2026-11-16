"""hr_answer: the record that makes a confirm or an edit idempotent

Revision ID: 0002
Revises: 0001

A repeated POST /hr/answers carries the same `dedup_key`. Without a stored record there is
nothing to find it by: the edit's rejudge jobs are deduplicated by the queue, but a position
has no assessments before phase 1.4b, so a replayed edit would otherwise bump the version
twice. Phase 3.3 may fold this into the question and rule tables.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE hr_answer (
    dedup_key       text PRIMARY KEY,
    position_id     uuid NOT NULL REFERENCES job_position (id) ON DELETE CASCADE,
    type            text NOT NULL
        CONSTRAINT hr_answer_type_check CHECK (type IN ('confirm', 'edit')),
    -- Hash of the whole request: the same key with different content is a client bug (409).
    request_sha256  text NOT NULL,
    -- The position's rubric_version after the answer, and what the answer enqueued, so a
    -- replay returns the original result.
    rubric_version  integer NOT NULL,
    rejudge_jobs    integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX hr_answer_position_idx ON hr_answer (position_id);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE hr_answer")
