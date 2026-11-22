"""Read-only endpoints: the ranked list of a position and one assessment (§2.0)."""

from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.services import assessment_reads

router = APIRouter()


class RankingRowOut(BaseModel):
    assessment_id: UUID
    candidate_name: str | None
    document_id: UUID | None
    filename: str | None
    status: Literal["done", "failed"]
    # Null unless the assessment is `done`.
    score: float | None
    # A mandatory requirement is `not_met`; such candidates rank below the rest.
    mandatory_failed: bool
    # Verdicts with any flag, including `list_only_skill`, whose quote is verified.
    flagged_verdicts: int
    # Verdicts flagged `quote_not_found` or `no_evidence`: their quotes are not evidence.
    # 0 for a `failed` assessment.
    unverified_quote_verdicts: int
    # Verdicts flagged `list_only_skill`: the skill appears only in a list. 0 when `failed`.
    list_only_verdicts: int
    rubric_version: int
    # Made against requirements HR has not confirmed yet.
    rubric_unconfirmed: bool


class PositionRankingOut(BaseModel):
    position_id: UUID
    rubric_version: int
    rubric_status: Literal["unconfirmed", "confirmed"]
    rows: list[RankingRowOut]


class EvidenceOut(BaseModel):
    quote: str
    # Offsets into `cv_text` of the assessment.
    char_start: int
    char_end: int


class FlagOut(BaseModel):
    code: str
    detail: str


class VerdictOut(BaseModel):
    requirement_id: UUID
    parent_id: UUID | None
    text: str
    kind: Literal["mandatory", "nice_to_have"]
    weight: int
    min_months: int | None
    verdict: Literal["met", "partial", "not_met"]
    rationale: str | None
    flags: list[FlagOut]
    # Null for `not_met` and for a flagged verdict: only a quote that exists in the CV is shown.
    evidence: EvidenceOut | None


class AssessmentOut(BaseModel):
    assessment_id: UUID
    position_id: UUID
    candidate_name: str | None
    document_id: UUID | None
    filename: str | None
    status: Literal["done", "failed"]
    score: float | None
    mandatory_failed: bool
    rubric_version: int
    rubric_unconfirmed: bool
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    # Why the assessment failed, when it did.
    error: str | None
    created_at: datetime
    updated_at: datetime
    # Flags of the CV document: low_coverage, suspected_injection.
    cv_flags: list[FlagOut]
    # Computed tenure facts: total_months, as_of, counted_items, skipped_items.
    tenure: dict[str, Any] | None
    # The CV's `raw_text`, rendered as text only; evidence offsets point into it.
    cv_text: str | None
    verdicts: list[VerdictOut]


@router.get("/positions/{position_id}/ranking")
def get_ranking(position_id: UUID, request: Request) -> PositionRankingOut:
    pool = cast(ConnectionPool, request.app.state.pool)
    with pool.connection() as conn:
        ranking = assessment_reads.get_position_ranking(conn, position_id)
    if ranking is None:
        raise HTTPException(404, "No such position")
    return PositionRankingOut.model_validate(asdict(ranking))


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: UUID, request: Request) -> AssessmentOut:
    pool = cast(ConnectionPool, request.app.state.pool)
    with pool.connection() as conn:
        detail = assessment_reads.get_assessment(conn, assessment_id)
    if detail is None:
        raise HTTPException(404, "No such assessment")
    return AssessmentOut.model_validate(asdict(detail))
