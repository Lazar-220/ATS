"""Read side of assessments: the ranked list of a position and one assessment with its evidence.

Read-only: nothing here triggers scoring (§2.0). A quote is returned as evidence only when code
verified it; a flagged verdict keeps its flag and its verdict but carries no evidence.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from ats.pipeline.quotes import NO_EVIDENCE, QUOTE_NOT_FOUND
from ats.pipeline.score import ranking_key

QUOTE_FLAGS = frozenset({QUOTE_NOT_FOUND, NO_EVIDENCE})


@dataclass(frozen=True)
class RankingRow:
    assessment_id: UUID
    candidate_name: str | None
    document_id: UUID | None
    filename: str | None
    status: str
    # None unless the assessment is `done`.
    score: float | None
    mandatory_failed: bool
    flagged_verdicts: int
    rubric_version: int
    # The label of §2.4: the assessment was made against requirements HR has not confirmed.
    rubric_unconfirmed: bool


@dataclass(frozen=True)
class PositionRanking:
    position_id: UUID
    rubric_version: int
    rubric_status: str
    rows: list[RankingRow]


@dataclass(frozen=True)
class Evidence:
    quote: str
    # Offsets into the CV's `raw_text`, which is `AssessmentDetail.cv_text`.
    char_start: int
    char_end: int


@dataclass(frozen=True)
class VerdictRow:
    requirement_id: UUID
    parent_id: UUID | None
    text: str
    kind: str
    weight: int
    min_months: int | None
    verdict: str
    rationale: str | None
    flags: list[dict[str, str]]
    evidence: Evidence | None


@dataclass(frozen=True)
class AssessmentDetail:
    assessment_id: UUID
    position_id: UUID
    candidate_name: str | None
    document_id: UUID | None
    filename: str | None
    status: str
    score: float | None
    mandatory_failed: bool
    rubric_version: int
    rubric_unconfirmed: bool
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    cv_flags: list[dict[str, str]]
    tenure: dict[str, Any] | None
    cv_text: str | None
    verdicts: list[VerdictRow]


def get_position_ranking(
    conn: psycopg.Connection[Any], position_id: UUID
) -> PositionRanking | None:
    position = conn.execute(
        "SELECT rubric_version, rubric_status FROM job_position WHERE id = %s", (position_id,)
    ).fetchone()
    if position is None:
        return None
    unconfirmed = position[1] != "confirmed"
    rows = conn.execute(
        "SELECT a.id, c.full_name, d.id, d.filename, a.status, a.score, a.mandatory_failed, "
        "a.rubric_version, a.created_at, "
        "(SELECT count(*) FROM verdict v WHERE v.assessment_id = a.id "
        " AND jsonb_array_length(v.flags) > 0) "
        "FROM assessment a JOIN candidate c ON c.id = a.candidate_id "
        "LEFT JOIN document d ON d.candidate_id = a.candidate_id "
        "WHERE a.position_id = %s",
        (position_id,),
    ).fetchall()

    def order(row: tuple[Any, ...]) -> tuple[Any, ...]:
        done = row[4] == "done"
        score = float(row[5]) if done and row[5] is not None else 0.0
        # `done` first, then unflagged before flagged, then the score, then arrival order.
        return (not done, *ranking_key(bool(row[6]), score), row[8], row[0])

    ranked = [
        RankingRow(
            assessment_id=row[0],
            candidate_name=row[1],
            document_id=row[2],
            filename=row[3],
            status=row[4],
            score=float(row[5]) if row[4] == "done" and row[5] is not None else None,
            mandatory_failed=bool(row[6]) and row[4] == "done",
            flagged_verdicts=int(row[9]),
            rubric_version=row[7],
            rubric_unconfirmed=unconfirmed,
        )
        for row in sorted(rows, key=order)
    ]
    return PositionRanking(position_id, position[0], position[1], ranked)


def _evidence(row: tuple[Any, ...]) -> Evidence | None:
    quote, start, end, flags = row[7], row[8], row[9], row[10]
    if quote is None or start is None or end is None:
        return None
    if any(flag["code"] in QUOTE_FLAGS for flag in flags):
        return None
    return Evidence(quote=quote, char_start=start, char_end=end)


def get_assessment(conn: psycopg.Connection[Any], assessment_id: UUID) -> AssessmentDetail | None:
    row = conn.execute(
        "SELECT a.id, a.position_id, c.full_name, d.id, d.filename, a.status, a.score, "
        "a.mandatory_failed, a.rubric_version, p.rubric_status, a.cost_usd, a.input_tokens, "
        "a.output_tokens, a.trace, a.created_at, a.updated_at, d.flags, d.parsed_json, d.raw_text "
        "FROM assessment a JOIN candidate c ON c.id = a.candidate_id "
        "JOIN job_position p ON p.id = a.position_id "
        "LEFT JOIN document d ON d.candidate_id = a.candidate_id "
        "WHERE a.id = %s",
        (assessment_id,),
    ).fetchone()
    if row is None:
        return None
    done = row[5] == "done"
    verdict_rows = conn.execute(
        "SELECT r.id, r.parent_id, r.text, r.kind, r.weight, r.min_months, v.verdict, "
        "v.quote, v.char_start, v.char_end, v.flags, v.rationale "
        "FROM verdict v JOIN requirement r ON r.id = v.requirement_id "
        "WHERE v.assessment_id = %s ORDER BY r.ord, r.id",
        (assessment_id,),
    ).fetchall()
    trace: dict[str, Any] = row[13] or {}
    parsed: dict[str, Any] | None = row[17]
    return AssessmentDetail(
        assessment_id=row[0],
        position_id=row[1],
        candidate_name=row[2],
        document_id=row[3],
        filename=row[4],
        status=row[5],
        score=float(row[6]) if done and row[6] is not None else None,
        mandatory_failed=bool(row[7]) and done,
        rubric_version=row[8],
        rubric_unconfirmed=row[9] != "confirmed",
        cost_usd=float(row[10]) if row[10] is not None else None,
        input_tokens=row[11],
        output_tokens=row[12],
        error=trace.get("error"),
        created_at=row[14],
        updated_at=row[15],
        cv_flags=row[16] or [],
        tenure=parsed.get("tenure") if parsed else None,
        cv_text=row[18],
        verdicts=[
            VerdictRow(
                requirement_id=v[0],
                parent_id=v[1],
                text=v[2],
                kind=v[3],
                weight=int(v[4]),
                min_months=v[5],
                verdict=v[6],
                rationale=v[11],
                flags=v[10],
                evidence=_evidence(v),
            )
            for v in verdict_rows
        ]
        if done
        else [],
    )
