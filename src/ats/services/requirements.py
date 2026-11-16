"""Writing a position's requirement rows: the shared step of position setup and HR edits."""

from typing import Any
from uuid import UUID, uuid4

import psycopg

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
