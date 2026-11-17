"""HR's answers to a position's requirements (endpoint 3): confirm, or edit the list (§2.4).

An answer runs in the caller's transaction, under a row lock on the position, so two answers
for one position never interleave.
"""

import hashlib
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field

from ats.db import task_queue
from ats.pipeline.requirements import RequirementList
from ats.services.requirements import insert_requirements

REJUDGE_JOB = "rejudge"


class ConfirmAnswer(BaseModel):
    type: Literal["confirm"]
    position_id: UUID
    # Chosen by the client for one intent (a UUID per button press); a repeat reuses it.
    dedup_key: str = Field(min_length=1, max_length=200)
    # The version HR was looking at.
    rubric_version: int


class EditAnswer(BaseModel):
    type: Literal["edit"]
    position_id: UUID
    dedup_key: str = Field(min_length=1, max_length=200)
    # The version HR started from; the edit replaces that list.
    rubric_version: int
    requirements: RequirementList


type HrAnswer = Annotated[ConfirmAnswer | EditAnswer, Field(discriminator="type")]


@dataclass(frozen=True)
class AnswerResult:
    position_id: UUID
    rubric_version: int
    rubric_status: str
    rejudge_jobs: int
    # True when this call only returned the result of an earlier identical one.
    duplicate: bool


class PositionNotFound(Exception):
    pass


class StaleRubric(Exception):
    """HR answered against a version that is no longer the current one."""

    def __init__(self, sent: int, current: int) -> None:
        super().__init__(
            f"the requirements are at version {current}, not {sent}; reload and try again"
        )


class DedupKeyReused(Exception):
    """The `dedup_key` was already used for a different request."""


def _request_hash(answer: ConfirmAnswer | EditAnswer) -> str:
    return hashlib.sha256(answer.model_dump_json().encode()).hexdigest()


def apply_answer(conn: psycopg.Connection[Any], answer: ConfirmAnswer | EditAnswer) -> AnswerResult:
    position = conn.execute(
        "SELECT rubric_version, rubric_status FROM job_position WHERE id = %s FOR UPDATE",
        (answer.position_id,),
    ).fetchone()
    if position is None:
        raise PositionNotFound(str(answer.position_id))
    current_version, status = position

    request_hash = _request_hash(answer)
    # Checked under the position lock: two concurrent requests with one key meet here in turn.
    earlier = conn.execute(
        "SELECT position_id, request_sha256, rubric_version, rejudge_jobs FROM hr_answer "
        "WHERE dedup_key = %s",
        (answer.dedup_key,),
    ).fetchone()
    if earlier is not None:
        if earlier[0] != answer.position_id or earlier[1] != request_hash:
            raise DedupKeyReused(answer.dedup_key)
        return AnswerResult(answer.position_id, earlier[2], status, earlier[3], duplicate=True)

    if answer.rubric_version != current_version:
        raise StaleRubric(answer.rubric_version, current_version)

    rejudge_jobs = 0
    if isinstance(answer, ConfirmAnswer):
        status = "confirmed"
        conn.execute(
            "UPDATE job_position SET rubric_status = 'confirmed' WHERE id = %s",
            (answer.position_id,),
        )
    else:
        # An edit leaves rubric_status as it is: only the Confirm button confirms.
        current_version += 1
        conn.execute(
            "UPDATE job_position SET rubric_version = %s WHERE id = %s",
            (current_version, answer.position_id),
        )
        insert_requirements(conn, answer.position_id, current_version, answer.requirements)
        rejudge_jobs = _enqueue_rejudges(conn, answer.position_id, current_version)

    conn.execute(
        "INSERT INTO hr_answer (dedup_key, position_id, type, request_sha256, rubric_version, "
        "rejudge_jobs) VALUES (%s, %s, %s, %s, %s, %s)",
        (
            answer.dedup_key,
            answer.position_id,
            answer.type,
            request_hash,
            current_version,
            rejudge_jobs,
        ),
    )
    return AnswerResult(answer.position_id, current_version, status, rejudge_jobs, duplicate=False)


def _enqueue_rejudges(conn: psycopg.Connection[Any], position_id: UUID, version: int) -> int:
    """One job per assessment of the position (handled by `ats.worker.judge`)."""
    assessments = conn.execute(
        "SELECT id FROM assessment WHERE position_id = %s ORDER BY created_at, id", (position_id,)
    ).fetchall()
    enqueued = 0
    for (assessment_id,) in assessments:
        job_id = task_queue.enqueue(
            conn,
            REJUDGE_JOB,
            {"assessment_id": str(assessment_id), "rubric_version": version},
            dedup_key=f"{REJUDGE_JOB}:{assessment_id}:{version}",
        )
        enqueued += job_id is not None
    return enqueued
