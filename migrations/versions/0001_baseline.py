"""v1 baseline: the nine tables of version 1

Revision ID: 0001
Revises:

Left out on purpose: the vector extension, `chunk` and the vector columns (phase 2.1),
the question and rule tables (phase 2.6), verdict `iteration`/`is_current` (v2).
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE job_position (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title           text,
    source_sha256   text NOT NULL UNIQUE,
    posting_text    text,
    rubric_version  integer NOT NULL DEFAULT 1,
    rubric_status   text NOT NULL DEFAULT 'unconfirmed'
        CONSTRAINT job_position_rubric_status_check
        CHECK (rubric_status IN ('unconfirmed', 'confirmed')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- A requirement edit inserts new rows under the new rubric_version and keeps the old ones,
-- so verdicts written against an earlier version never dangle. The current set is the rows
-- whose rubric_version equals job_position.rubric_version.
CREATE TABLE requirement (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id     uuid NOT NULL REFERENCES job_position (id) ON DELETE CASCADE,
    parent_id       uuid REFERENCES requirement (id),
    rubric_version  integer NOT NULL,
    ord             integer NOT NULL DEFAULT 0,
    text            text NOT NULL,
    kind            text NOT NULL
        CONSTRAINT requirement_kind_check CHECK (kind IN ('mandatory', 'nice_to_have')),
    weight          numeric NOT NULL DEFAULT 1,
    min_months      integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX requirement_position_version_idx ON requirement (position_id, rubric_version);

-- The only table that holds name, email, phone and address; nothing here goes to the LLM.
CREATE TABLE candidate (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name   text,
    email       text,
    phone       text,
    address     text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            text NOT NULL
        CONSTRAINT document_kind_check CHECK (kind IN ('cv', 'posting')),
    sha256          text NOT NULL UNIQUE,
    filename        text,
    storage_path    text,
    candidate_id    uuid REFERENCES candidate (id),
    status          text NOT NULL DEFAULT 'uploaded'
        CONSTRAINT document_status_check
        CHECK (status IN ('uploaded', 'extracted', 'rejected', 'parsed', 'failed')),
    status_message  text,
    raw_text        text,
    masked_text     text,
    parsed_json     jsonb,
    lang            text,
    script          text,
    flags           jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ranking_request (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type         text NOT NULL
        CONSTRAINT ranking_request_type_check CHECK (type IN ('submit', 'search')),
    position_id  uuid NOT NULL REFERENCES job_position (id) ON DELETE CASCADE,
    status       text NOT NULL DEFAULT 'queued'
        CONSTRAINT ranking_request_status_check
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    top_n        integer,
    top_k        integer,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- document_id, not candidate_id, is the key: the rows are created at upload time and the
-- candidate only exists after CV parsing (phase 1.4a).
CREATE TABLE request_candidate (
    request_id       uuid NOT NULL REFERENCES ranking_request (id) ON DELETE CASCADE,
    document_id      uuid NOT NULL REFERENCES document (id),
    candidate_id     uuid REFERENCES candidate (id),
    prefilter_score  real,
    PRIMARY KEY (request_id, document_id)
);

-- No CHECK on status: v2 replaces it with a seven-state machine.
CREATE TABLE assessment (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id       uuid NOT NULL REFERENCES job_position (id) ON DELETE CASCADE,
    candidate_id      uuid NOT NULL REFERENCES candidate (id),
    rubric_version    integer NOT NULL,
    status            text NOT NULL DEFAULT 'queued',
    score             numeric,
    score_low         numeric,
    score_high        numeric,
    mandatory_failed  boolean NOT NULL DEFAULT false,
    cost_usd          numeric,
    input_tokens      integer,
    output_tokens     integer,
    trace             jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, position_id)
);

-- requirement_id has no ON DELETE CASCADE: a requirement a verdict points at must not vanish.
-- The check is deferred to commit: deleting a position cascades into requirement and into
-- assessment -> verdict as separate inner statements, and an immediate check would fire on the
-- requirement rows before the verdicts are gone.
CREATE TABLE verdict (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id  uuid NOT NULL REFERENCES assessment (id) ON DELETE CASCADE,
    requirement_id uuid NOT NULL REFERENCES requirement (id) DEFERRABLE INITIALLY DEFERRED,
    verdict        text NOT NULL
        CONSTRAINT verdict_verdict_check CHECK (verdict IN ('met', 'partial', 'not_met')),
    quote          text,
    char_start     integer,
    char_end       integer,
    rationale      text,
    flags          jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (assessment_id, requirement_id)
);
COMMENT ON COLUMN verdict.char_start IS
    'Start offset of the quote in document.raw_text of the candidate''s CV (plan 2.3, 3.2)';
COMMENT ON COLUMN verdict.char_end IS
    'End offset of the quote in document.raw_text of the candidate''s CV (plan 2.3, 3.2)';

CREATE TABLE task_queue (
    id            bigserial PRIMARY KEY,
    job_type      text NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        text NOT NULL DEFAULT 'queued'
        CONSTRAINT task_queue_status_check
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    dedup_key     text UNIQUE,
    attempts      integer NOT NULL DEFAULT 0,
    max_attempts  integer NOT NULL DEFAULT 3,
    error         text,
    locked_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_queue_status_id_idx ON task_queue (status, id);
"""

TABLES = (
    "task_queue",
    "verdict",
    "assessment",
    "request_candidate",
    "ranking_request",
    "document",
    "candidate",
    "requirement",
    "job_position",
)


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE {table}")
