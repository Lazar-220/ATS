"""Writing a position's requirement rows: the shared step of position setup and HR edits."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg

from ats.db import task_queue
from ats.pipeline.requirements import RequirementList

POSITION_SETUP_JOB = "position_setup"


def insert_requirements(
    conn: psycopg.Connection[Any],
    position_id: UUID,
    rubric_version: int,
    requirements: RequirementList,
) -> None:
    """Insert one rubric version. Older versions stay, so verdicts never dangle (1.1a).

    The list's `id` and `parent` labels become row ids: every row is inserted first and the
    parent links are set after, because the foreign key is checked per statement.
    """
    row_ids = {draft.id: uuid4() for draft in requirements.requirements}
    for order, draft in enumerate(requirements.requirements):
        conn.execute(
            "INSERT INTO requirement (id, position_id, rubric_version, ord, text, kind, weight, "
            "min_months) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                row_ids[draft.id],
                position_id,
                rubric_version,
                order,
                draft.text,
                draft.kind,
                draft.weight,
                draft.min_months,
            ),
        )
    for draft in requirements.requirements:
        if draft.parent is not None:
            conn.execute(
                "UPDATE requirement SET parent_id = %s WHERE id = %s",
                (row_ids[draft.parent], row_ids[draft.id]),
            )


def retry_failed_setup(conn: psycopg.Connection[Any], position_id: UUID) -> bool:
    """Put a setup job that ran out of attempts back in the queue; True if it did.

    Called when the same posting is uploaded again, which is HR's way to say "try again". The
    job row is reused (its dedup key is unique for all time) and one atomic UPDATE means that of
    two concurrent re-uploads only one requeues it.
    """
    requeued = conn.execute(
        "UPDATE task_queue SET status = 'queued', attempts = 0, error = NULL, locked_at = NULL, "
        "updated_at = now() WHERE dedup_key = %s AND status = 'failed' RETURNING id",
        (f"{POSITION_SETUP_JOB}:{position_id}",),
    ).fetchone()
    return requeued is not None


def enqueue_missing_setup(conn: psycopg.Connection[Any], position_id: UUID) -> bool:
    """Enqueue setup for a position that has its posting text but never got a job; True if it did.

    Ingest enqueues setup only when it extracts a posting, so a posting extracted before setup
    existed (or by a run that crashed between the two steps) would keep its position without
    requirements, and every CV submitted for it would wait forever. Uploading the posting again
    is HR asking for it to be fixed. The dedup key keeps this a no-op when any job exists.
    """
    stranded = conn.execute(
        "SELECT 1 FROM job_position p WHERE p.id = %s AND p.posting_text IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM requirement r WHERE r.position_id = p.id)",
        (position_id,),
    ).fetchone()
    return stranded is not None and enqueue_setup(conn, position_id)


@dataclass(frozen=True)
class StrandedPosition:
    id: UUID
    filename: str | None


class PositionPrefixError(Exception):
    """A position id prefix matched no position, or more than one."""


def find_stranded_positions(
    conn: psycopg.Connection[Any], prefix: str | None = None
) -> list[StrandedPosition]:
    """Positions whose setup was never enqueued: posting text, no requirements, no setup job.

    A position that has a setup job in any state is not stranded: a running or done one needs
    nothing, and a failed one is retried by uploading its posting again (`retry_failed_setup`).
    `prefix` narrows the search to ids that start with it, and must match exactly one position
    among all positions (not only the stranded ones), so a typo cannot select the wrong one.
    """
    if prefix is not None:
        matches = conn.execute(
            "SELECT id FROM job_position WHERE id::text LIKE %s", (prefix.lower() + "%",)
        ).fetchall()
        if len(matches) != 1:
            raise PositionPrefixError(
                f"{prefix!r} matches {len(matches)} positions; give a longer id"
                if matches
                else f"{prefix!r} matches no position"
            )
    rows = conn.execute(
        "SELECT p.id, d.filename FROM job_position p "
        "LEFT JOIN document d ON d.sha256 = p.source_sha256 "
        "WHERE p.posting_text IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM requirement r WHERE r.position_id = p.id) "
        "AND NOT EXISTS (SELECT 1 FROM task_queue t "
        "                WHERE t.dedup_key = %(job)s || p.id::text) "
        "AND (%(prefix)s::text IS NULL OR p.id::text LIKE %(prefix)s::text || '%%') "
        "ORDER BY p.created_at, p.id",
        {"job": f"{POSITION_SETUP_JOB}:", "prefix": prefix.lower() if prefix else None},
    ).fetchall()
    return [StrandedPosition(id=row[0], filename=row[1]) for row in rows]


def enqueue_setup(conn: psycopg.Connection[Any], position_id: UUID) -> bool:
    """Enqueue the setup job under the same dedup key ingest uses; False if one exists."""
    job_id = task_queue.enqueue(
        conn,
        POSITION_SETUP_JOB,
        {"position_id": str(position_id)},
        dedup_key=f"{POSITION_SETUP_JOB}:{position_id}",
    )
    return job_id is not None
