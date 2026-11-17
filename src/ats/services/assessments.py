"""Queueing the judge for a position's candidates.

A judge job needs two things that arrive independently: the candidate (CV parsing finished) and
the position's requirements (setup finished). Whichever comes last calls `enqueue_judgements`,
and the dedup key makes the call harmless when the other one already did.
"""

from typing import Any
from uuid import UUID

import psycopg

from ats.db import task_queue

JUDGE_JOB = "judge"


def judge_dedup_key(candidate_id: UUID, position_id: UUID, rubric_version: int) -> str:
    return f"{JUDGE_JOB}:{candidate_id}:{position_id}:{rubric_version}"


def enqueue_judgements(
    conn: psycopg.Connection[Any],
    position_id: UUID,
    *,
    retry_failed: bool = False,
) -> int:
    """Enqueue one judge job per candidate of the position that is not yet assessed.

    Does nothing while the position has no requirements. `retry_failed` puts a judge job that ran
    out of attempts back in the queue: uploading the same CV again is HR asking to try again.
    Returns the number of jobs enqueued or requeued.
    """
    position = conn.execute(
        "SELECT p.rubric_version FROM job_position p WHERE p.id = %s "
        "AND EXISTS (SELECT 1 FROM requirement r WHERE r.position_id = p.id "
        "            AND r.rubric_version = p.rubric_version)",
        (position_id,),
    ).fetchone()
    if position is None:
        return 0
    version: int = position[0]
    candidates = conn.execute(
        "SELECT DISTINCT rc.candidate_id FROM request_candidate rc "
        "JOIN ranking_request rr ON rr.id = rc.request_id "
        "WHERE rr.position_id = %s AND rc.candidate_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM assessment a WHERE a.candidate_id = rc.candidate_id "
        "                AND a.position_id = rr.position_id AND a.rubric_version = %s "
        "                AND a.status = 'done') "
        "ORDER BY rc.candidate_id",
        (position_id, version),
    ).fetchall()
    enqueued = 0
    for (candidate_id,) in candidates:
        key = judge_dedup_key(candidate_id, position_id, version)
        job_id = task_queue.enqueue(
            conn,
            JUDGE_JOB,
            {"candidate_id": str(candidate_id), "position_id": str(position_id)},
            dedup_key=key,
        )
        if job_id is not None:
            enqueued += 1
        elif retry_failed:
            requeued = conn.execute(
                "UPDATE task_queue SET status = 'queued', attempts = 0, error = NULL, "
                "locked_at = NULL, updated_at = now() "
                "WHERE dedup_key = %s AND status = 'failed' RETURNING id",
                (key,),
            ).fetchone()
            enqueued += requeued is not None
    return enqueued


def enqueue_judgements_for_document(conn: psycopg.Connection[Any], document_id: UUID) -> int:
    """After a CV is parsed: judge it against every position it was submitted for."""
    positions = conn.execute(
        "SELECT DISTINCT rr.position_id FROM request_candidate rc "
        "JOIN ranking_request rr ON rr.id = rc.request_id WHERE rc.document_id = %s",
        (document_id,),
    ).fetchall()
    return sum(enqueue_judgements(conn, position_id) for (position_id,) in positions)
