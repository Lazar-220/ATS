"""The read endpoints, over assessments the worker wrote and over seeded rows."""

from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.llm.fake import FakeLLMClient
from integration.test_ingest import upload, wait_until_settled
from integration.test_judge import CV, POSTING, QUOTE, _script

pytestmark = pytest.mark.integration


def test_the_assessment_shows_verified_evidence_and_hides_a_flagged_quote(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    _script(fake_llm, {1: ("met", QUOTE), 2: ("partial", "Led a team of fifteen engineers")})
    accepted = upload(client, POSTING, [CV])
    wait_until_settled(conn)

    ranking = client.get(f"/positions/{accepted['position_id']}/ranking").json()
    assert (ranking["rubric_status"], ranking["rubric_version"]) == ("unconfirmed", 1)
    (row,) = ranking["rows"]
    assert row["status"] == "done" and row["score"] == 75.0 and row["flagged_verdicts"] == 1
    assert row["rubric_unconfirmed"] is True and row["filename"] == "cv0.pdf"

    body = client.get(f"/assessments/{row['assessment_id']}").json()
    assert body["rubric_unconfirmed"] is True and body["status"] == "done"
    first, second = body["verdicts"]
    evidence = first["evidence"]
    assert body["cv_text"][evidence["char_start"] : evidence["char_end"]] == QUOTE
    assert evidence["quote"] == QUOTE
    # Flagged: the verdict and the flag stay, the quote is not offered as evidence.
    assert (second["verdict"], second["evidence"]) == ("partial", None)
    assert [flag["code"] for flag in second["flags"]] == ["quote_not_found"]
    assert body["tenure"]["total_months"] == 0

    client.post(
        "/hr/answers",
        json={
            "type": "confirm",
            "position_id": accepted["position_id"],
            "dedup_key": "c1",
            "rubric_version": 1,
        },
    )
    after = client.get(f"/assessments/{row['assessment_id']}").json()
    assert after["rubric_unconfirmed"] is False


def _seed(conn: psycopg.Connection[DictRow]) -> tuple[UUID, dict[str, UUID]]:
    position = conn.execute(
        "INSERT INTO job_position (source_sha256, rubric_status) VALUES ('p', 'confirmed') "
        "RETURNING id"
    ).fetchone()
    assert position is not None
    ids: dict[str, UUID] = {}
    cases: list[tuple[str, str, float | None, bool]] = [
        ("low", "done", 40, False),
        ("high_failed", "done", 90, True),
        ("high", "done", 80, False),
        ("broken", "failed", None, False),
    ]
    for name, status, score, failed in cases:
        candidate = conn.execute(
            "INSERT INTO candidate (full_name) VALUES (%s) RETURNING id", (name,)
        ).fetchone()
        assert candidate is not None
        assessment = conn.execute(
            "INSERT INTO assessment (position_id, candidate_id, rubric_version, status, score, "
            "mandatory_failed) VALUES (%s, %s, 1, %s, %s, %s) RETURNING id",
            (position["id"], candidate["id"], status, score, failed),
        ).fetchone()
        assert assessment is not None
        ids[name] = assessment["id"]
    return position["id"], ids


def test_ranking_order_is_done_first_then_unflagged_then_score(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    position_id, _ = _seed(conn)
    body: Any = client.get(f"/positions/{position_id}/ranking").json()
    assert [row["candidate_name"] for row in body["rows"]] == [
        "high",
        "low",
        "high_failed",
        "broken",
    ]
    assert body["rows"][0]["rubric_unconfirmed"] is False
    assert body["rows"][-1]["score"] is None


def test_unknown_ids_are_404_and_a_malformed_one_is_422(client: TestClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/positions/{unknown}/ranking").status_code == 404
    assert client.get(f"/assessments/{unknown}").status_code == 404
    assert client.get("/assessments/nope").status_code == 422
