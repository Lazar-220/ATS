from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.services import hr_answers
from ats.services.hr_answers import (
    DedupKeyReused,
    HrAnswer,
    PositionNotFound,
    StaleRubric,
)

router = APIRouter()


class AnswerOut(BaseModel):
    position_id: UUID
    rubric_version: int
    rubric_status: Literal["unconfirmed", "confirmed"]
    # Re-judge jobs this answer enqueued; they are handled from phase 1.4b.
    rejudge_jobs: int
    # True when the request repeated an earlier one and nothing was done again.
    duplicate: bool


@router.post("/hr/answers")
def post_answer(answer: HrAnswer, request: Request) -> AnswerOut:
    pool = cast(ConnectionPool, request.app.state.pool)
    try:
        with pool.connection() as conn:
            result = hr_answers.apply_answer(conn, answer)
    except PositionNotFound as exc:
        raise HTTPException(404, "No such position") from exc
    except (StaleRubric, DedupKeyReused) as exc:
        raise HTTPException(409, str(exc)) from exc
    return AnswerOut(
        position_id=result.position_id,
        rubric_version=result.rubric_version,
        rubric_status=cast(Literal["unconfirmed", "confirmed"], result.rubric_status),
        rejudge_jobs=result.rejudge_jobs,
        duplicate=result.duplicate,
    )
