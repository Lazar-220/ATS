"""Read side of positions: the list and one position with its current requirements.

Read-only: nothing here triggers scoring or setup (§2.0).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg

from ats.services.requirements import POSITION_SETUP_JOB

type SetupStatus = Literal["pending", "running", "done", "failed"]

SETUP_FAILED_MESSAGE = "Extracting the requirements failed. Upload the posting again to retry."

_SELECT = (
    "SELECT p.id, p.rubric_status, p.rubric_version, p.created_at, d.filename, "
    "d.status, d.status_message, "
    "(SELECT count(*) FROM requirement r "
    " WHERE r.position_id = p.id AND r.rubric_version = p.rubric_version), "
    "(SELECT t.status FROM task_queue t WHERE t.dedup_key = %(setup_prefix)s || p.id::text) "
    "FROM job_position p LEFT JOIN document d ON d.sha256 = p.source_sha256 "
)


@dataclass(frozen=True)
class PositionSummary:
    id: UUID
    filename: str | None
    rubric_status: Literal["unconfirmed", "confirmed"]
    rubric_version: int
    created_at: datetime
    requirement_count: int
    setup_status: SetupStatus
    # Why setup is not `done`, written for HR; None otherwise.
    setup_message: str | None


@dataclass(frozen=True)
class RequirementRow:
    id: UUID
    parent_id: UUID | None
    text: str
    kind: Literal["mandatory", "nice_to_have"]
    weight: int
    min_months: int | None


@dataclass(frozen=True)
class PositionDetail:
    summary: PositionSummary
    requirements: list[RequirementRow]


def _summary(row: tuple[Any, ...]) -> PositionSummary:
    (position_id, rubric_status, version, created_at, filename, doc_status, doc_message) = row[:7]
    count, job_status = row[7], row[8]
    status: SetupStatus
    message: str | None = None
    # Derived at read time like the request status: setup has no state of its own to keep in step.
    if count > 0:
        status = "done"
    elif doc_status in ("rejected", "failed"):
        status, message = "failed", doc_message
    elif job_status == "failed":
        status, message = "failed", SETUP_FAILED_MESSAGE
    elif job_status in ("queued", "running"):
        status = "running"
    else:
        status = "pending"  # the posting text is not extracted yet
    return PositionSummary(
        id=position_id,
        filename=filename,
        rubric_status=rubric_status,
        rubric_version=version,
        created_at=created_at,
        requirement_count=count,
        setup_status=status,
        setup_message=message,
    )


def list_positions(conn: psycopg.Connection[Any]) -> list[PositionSummary]:
    rows = conn.execute(
        _SELECT + "ORDER BY p.created_at DESC, p.id", {"setup_prefix": f"{POSITION_SETUP_JOB}:"}
    ).fetchall()
    return [_summary(row) for row in rows]


def get_position(conn: psycopg.Connection[Any], position_id: UUID) -> PositionDetail | None:
    row = conn.execute(
        _SELECT + "WHERE p.id = %(id)s",
        {"setup_prefix": f"{POSITION_SETUP_JOB}:", "id": position_id},
    ).fetchone()
    if row is None:
        return None
    summary = _summary(row)
    requirements = conn.execute(
        "SELECT id, parent_id, text, kind, weight, min_months FROM requirement "
        "WHERE position_id = %s AND rubric_version = %s ORDER BY ord",
        (position_id, summary.rubric_version),
    ).fetchall()
    return PositionDetail(
        summary=summary,
        requirements=[
            RequirementRow(r[0], r[1], r[2], r[3], int(r[4]), r[5]) for r in requirements
        ],
    )
