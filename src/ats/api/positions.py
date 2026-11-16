from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.services import positions
from ats.services.positions import PositionSummary

router = APIRouter()


class PositionOut(BaseModel):
    id: UUID
    # The posting's file name: positions have no title of their own yet.
    filename: str | None
    rubric_status: Literal["unconfirmed", "confirmed"]
    rubric_version: int
    created_at: datetime
    requirement_count: int
    setup_status: Literal["pending", "running", "done", "failed"]
    setup_message: str | None


class RequirementOut(BaseModel):
    id: UUID
    parent_id: UUID | None
    text: str
    kind: Literal["mandatory", "nice_to_have"]
    weight: int
    min_months: int | None


class PositionDetailOut(PositionOut):
    # The current rubric version only; older versions stay in the database for old verdicts.
    requirements: list[RequirementOut]


def _out(summary: PositionSummary) -> PositionOut:
    return PositionOut(**summary.__dict__)


@router.get("/positions")
def list_positions(request: Request) -> list[PositionOut]:
    pool = cast(ConnectionPool, request.app.state.pool)
    with pool.connection() as conn:
        return [_out(summary) for summary in positions.list_positions(conn)]


@router.get("/positions/{position_id}")
def get_position(position_id: UUID, request: Request) -> PositionDetailOut:
    pool = cast(ConnectionPool, request.app.state.pool)
    with pool.connection() as conn:
        detail = positions.get_position(conn, position_id)
    if detail is None:
        raise HTTPException(404, "No such position")
    return PositionDetailOut(
        **_out(detail.summary).model_dump(),
        requirements=[RequirementOut(**row.__dict__) for row in detail.requirements],
    )
