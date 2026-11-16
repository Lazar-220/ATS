"""Job queue over the `task_queue` table.

Every operation is one SQL statement, so it is atomic on its own and needs no explicit
transaction. Delivery is at-least-once: a job whose worker dies is handed out again, so
handlers must be idempotent.
"""

from dataclasses import dataclass
from typing import Any, Literal

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

DEFAULT_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Job:
    id: int
    job_type: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def enqueue(
    conn: psycopg.Connection[Any],
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    dedup_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> int | None:
    """Add a job. Returns its id, or None when `dedup_key` already names a job."""
    row = conn.execute(
        "INSERT INTO task_queue (job_type, payload, dedup_key, max_attempts) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (dedup_key) DO NOTHING RETURNING id",
        (job_type, Jsonb(payload or {}), dedup_key, max_attempts),
    ).fetchone()
    return None if row is None else int(row[0])


def claim(conn: psycopg.Connection[Any]) -> Job | None:
    """Take the oldest queued job. SKIP LOCKED lets concurrent workers pass each other."""
    with conn.cursor(row_factory=class_row(Job)) as cur:
        cur.execute(
            "UPDATE task_queue SET status = 'running', attempts = attempts + 1, "
            "locked_at = now(), updated_at = now() "
            "WHERE id = ("
            "  SELECT id FROM task_queue WHERE status = 'queued' "
            "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
            ") RETURNING id, job_type, payload, attempts, max_attempts"
        )
        return cur.fetchone()


def complete(conn: psycopg.Connection[Any], job: Job) -> bool:
    """Mark a claimed job done. False means the job was handed to someone else meanwhile."""
    cur = conn.execute(
        "UPDATE task_queue SET status = 'done', locked_at = NULL, error = NULL, "
        "updated_at = now() WHERE id = %s AND status = 'running' AND attempts = %s",
        (job.id, job.attempts),
    )
    return cur.rowcount == 1


def fail(
    conn: psycopg.Connection[Any], job: Job, error: str
) -> Literal["requeued", "failed", "lost"]:
    """Record an error. The job is retried until its attempts are used up, then stays `failed`."""
    row = conn.execute(
        "UPDATE task_queue SET "
        "status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END, "
        "error = %s, locked_at = NULL, updated_at = now() "
        "WHERE id = %s AND status = 'running' AND attempts = %s RETURNING status",
        (error, job.id, job.attempts),
    ).fetchone()
    if row is None:
        return "lost"
    return "failed" if row[0] == "failed" else "requeued"


def requeue_stale(conn: psycopg.Connection[Any], visibility_timeout_s: float) -> int:
    """Release jobs stuck in `running` longer than the timeout (their worker died).

    The abandoned run already counted as an attempt, so a job that keeps killing its worker
    ends as `failed` instead of looping forever.
    """
    cur = conn.execute(
        "UPDATE task_queue SET "
        "status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END, "
        "error = 'visibility timeout: worker did not finish the job', "
        "locked_at = NULL, updated_at = now() "
        "WHERE status = 'running' AND locked_at < now() - make_interval(secs => %s)",
        (visibility_timeout_s,),
    )
    return cur.rowcount
