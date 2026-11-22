"""The read endpoints, over assessments the worker wrote and over seeded rows."""

from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb
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
    assert (row["unverified_quote_verdicts"], row["list_only_verdicts"]) == (1, 0)
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


def _flag(code: str) -> list[dict[str, str]]:
    return [{"code": code, "detail": "seeded"}]


def test_flag_counts_split_unverified_quotes_from_list_only_skills(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    position_id, ids = _seed(conn)
    flag_sets: list[list[dict[str, str]]] = [
        _flag("quote_not_found"),
        _flag("no_evidence"),
        _flag("list_only_skill"),
        _flag("list_only_skill"),
        [],
    ]
    requirements: list[UUID] = []
    for index in range(len(flag_sets)):
        requirement = conn.execute(
            "INSERT INTO requirement (position_id, rubric_version, ord, text, kind) "
            "VALUES (%s, 1, %s, %s, 'mandatory') RETURNING id",
            (position_id, index, f"skill {index}"),
        ).fetchone()
        assert requirement is not None
        requirements.append(requirement["id"])
    # The same verdicts on a done assessment and on a failed one (a re-judge that gave up
    # keeps the verdicts of the earlier run).
    for name in ("high", "broken"):
        for requirement_id, flags in zip(requirements, flag_sets, strict=True):
            conn.execute(
                "INSERT INTO verdict (assessment_id, requirement_id, verdict, flags) "
                "VALUES (%s, %s, 'partial', %s)",
                (ids[name], requirement_id, Jsonb(flags)),
            )

    rows = {
        row["candidate_name"]: row
        for row in client.get(f"/positions/{position_id}/ranking").json()["rows"]
    }

    counts = ("flagged_verdicts", "unverified_quote_verdicts", "list_only_verdicts")
    assert tuple(rows["high"][key] for key in counts) == (4, 2, 2)
    assert tuple(rows["broken"][key] for key in counts) == (4, 0, 0)  # flagged_verdicts as before
    assert tuple(rows["low"][key] for key in counts) == (0, 0, 0)


def test_unknown_ids_are_404_and_a_malformed_one_is_422(client: TestClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/positions/{unknown}/ranking").status_code == 404
    assert client.get(f"/assessments/{unknown}").status_code == 404
    assert client.get("/assessments/nope").status_code == 422
