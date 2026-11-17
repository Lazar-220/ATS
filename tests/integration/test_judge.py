"""The judge pipeline end to end: upload, the real worker loop, then the database."""

import re
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.llm.fake import FakeLLMClient
from ats.llm.types import LLMRequest
from ats.pipeline.judge import JudgeOutput, RequirementVerdict
from ats.pipeline.parsing import ParsedCV
from ats.pipeline.requirements import RequirementDraft, RequirementList
from integration.test_ingest import upload, wait_until_settled

pytestmark = pytest.mark.integration

POSTING = make_pdf("Senior Python developer, Belgrade\n" + "Zahtevi: pet godina iskustva. " * 6)
CV_TEXT = "Led a team of eight people at a bank, 2019-2023.\n" * 6
CV = make_pdf(CV_TEXT)
QUOTE = "Led a team of eight people at a bank"


def _calls(fake: FakeLLMClient, kind: str) -> int:
    return sum(1 for call in fake.calls if call.prompt_version.startswith(kind))


def _script(fake: FakeLLMClient, verdicts: dict[int, tuple[str, str | None]]) -> None:
    """Two requirements; the judge answers as `verdicts` says (label -> verdict, quote)."""
    drafts = [
        RequirementDraft(
            id=i, text=f"Requirement {i}", kind="mandatory", weight=1, min_months=None, parent=None
        )
        for i in (1, 2)
    ]

    def answer(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        if schema is ParsedCV:
            return ParsedCV(
                is_cv=True,
                suspected_injection=False,
                experience=[],
                education=[],
                skills=[],
                certificates=[],
                languages=[],
                projects=[],
            )
        if schema is JudgeOutput:
            ids = [int(i) for i in re.findall(r"^- id (\d+) ", request.user, re.MULTILINE)]
            return JudgeOutput(
                verdicts=[
                    RequirementVerdict(
                        requirement_id=i,
                        verdict=verdicts[i][0],  # type: ignore[arg-type]
                        quote=verdicts[i][1],
                        rationale="because",
                    )
                    for i in ids
                ]
            )
        return RequirementList(requirements=drafts)

    fake.responder = answer


def test_a_cv_is_judged_quotes_are_checked_and_the_score_is_stored(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    _script(fake_llm, {1: ("met", QUOTE), 2: ("met", "Led a team of fifteen engineers at Google")})
    accepted = upload(client, POSTING, [CV])
    wait_until_settled(conn)

    assessment = conn.execute("SELECT * FROM assessment").fetchone()
    assert assessment is not None
    assert assessment["status"] == "done" and assessment["rubric_version"] == 1
    assert float(assessment["score"]) == 100.0  # the judge's verdicts stand, flagged or not
    assert assessment["trace"]["prompt_version"] == "judge_v1"
    verdicts = conn.execute(
        "SELECT v.*, r.ord FROM verdict v JOIN requirement r ON r.id = v.requirement_id "
        "ORDER BY r.ord"
    ).fetchall()
    first, second = verdicts
    raw = conn.execute("SELECT raw_text FROM document WHERE kind = 'cv'").fetchone()
    assert raw is not None
    assert first["flags"] == []
    assert raw["raw_text"][first["char_start"] : first["char_end"]] == QUOTE
    assert [flag["code"] for flag in second["flags"]] == ["quote_not_found"]
    assert second["char_start"] is None and second["verdict"] == "met"
    assert _calls(fake_llm, "judge") == 1
    status = client.get(f"/rankings/{accepted['request_id']}").json()["status"]
    assert status == "done"


def test_the_same_cv_and_posting_again_costs_no_llm_call(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    _script(fake_llm, {1: ("met", QUOTE), 2: ("not_met", None)})
    upload(client, POSTING, [CV])
    wait_until_settled(conn)
    calls = len(fake_llm.calls)

    again = upload(client, POSTING, [CV])
    wait_until_settled(conn)

    assert len(fake_llm.calls) == calls
    assert conn.execute("SELECT count(*) AS n FROM assessment").fetchone() == {"n": 1}
    linked = conn.execute(
        "SELECT candidate_id FROM request_candidate WHERE request_id = %s", (again["request_id"],)
    ).fetchone()
    assert linked is not None and linked["candidate_id"] is not None
    assert client.get(f"/rankings/{again['request_id']}").json()["status"] == "done"


def test_editing_the_requirements_rescores_the_cv_without_a_manual_step(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    _script(fake_llm, {1: ("met", QUOTE), 2: ("not_met", None)})
    accepted = upload(client, POSTING, [CV])
    wait_until_settled(conn)
    before = conn.execute("SELECT id, score FROM assessment").fetchone()
    assert before is not None and float(before["score"]) == 50.0

    response = client.post(
        "/hr/answers",
        json={
            "type": "edit",
            "position_id": accepted["position_id"],
            "dedup_key": "edit-1",
            "rubric_version": 1,
            "requirements": {
                "requirements": [
                    {
                        "id": 1,
                        "text": "Only this",
                        "kind": "mandatory",
                        "weight": 2,
                        "min_months": None,
                        "parent": None,
                    }
                ]
            },
        },
    )
    assert response.json()["rejudge_jobs"] == 1
    _script(fake_llm, {1: ("met", QUOTE), 2: ("not_met", None)})  # same answers, one requirement
    wait_until_settled(conn)

    def rescored() -> Any:
        return conn.execute(
            "SELECT a.id, a.rubric_version, a.score, count(v.id) AS verdicts FROM assessment a "
            "JOIN verdict v ON v.assessment_id = a.id GROUP BY a.id"
        ).fetchone()

    row = rescored()
    assert row is not None
    assert row["id"] == before["id"]  # one assessment per pair, judged again in place
    assert (row["rubric_version"], float(row["score"]), row["verdicts"]) == (2, 100.0, 1)
