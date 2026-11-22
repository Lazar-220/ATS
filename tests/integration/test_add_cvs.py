"""POST /positions/{id}/cvs: the same request as POST /rankings, with the position's own posting.

Fake model and synthetic PDFs only; the real worker loop runs on a thread.
"""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from psycopg import sql
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.llm.fake import FakeLLMClient
from ats.settings import get_settings
from integration.test_ingest import upload, wait_until_settled
from integration.test_reupload import (
    CV_NEW,
    CV_OLD,
    CV_SCAN,
    POSTING,
    _assessments,
    _forget_setup_and_judgements,
    _judge_calls,
    _status,
)

pytestmark = pytest.mark.integration

CV_THIRD = make_pdf("Designed data pipelines in Python and SQL for four years.\n" * 6)
UNKNOWN = "00000000-0000-0000-0000-000000000000"


def add(client: TestClient, position_id: str, cvs: list[bytes], prefix: str = "add") -> Any:
    files = [("cvs", (f"{prefix}{i}.pdf", cv, "application/pdf")) for i, cv in enumerate(cvs)]
    return client.post(f"/positions/{position_id}/cvs", files=files)


def _added(client: TestClient, position_id: str, cvs: list[bytes]) -> Any:
    response = add(client, position_id, cvs)
    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"request_id", "position_id"} and body["position_id"] == position_id
    return body


def _count(conn: psycopg.Connection[DictRow], table: str) -> int:
    query = sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
    row = conn.execute(query).fetchone()
    assert row is not None
    return int(row["n"])


def test_cvs_added_to_a_known_position_are_ranked_and_the_posting_is_listed_first(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    first = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    added = _added(client, first["position_id"], [CV_NEW, CV_THIRD])
    assert added["request_id"] != first["request_id"]
    wait_until_settled(conn)

    state = _status(client, added["request_id"])
    assert state["status"] == "done"
    assert [(d["kind"], d["filename"]) for d in state["documents"]] == [
        ("posting", "posting.pdf"),
        ("cv", "add0.pdf"),
        ("cv", "add1.pdf"),
    ]
    ranking = client.get(f"/positions/{first['position_id']}/ranking").json()
    assert sorted(row["filename"] for row in ranking["rows"]) == ["add0.pdf", "add1.pdf", "cv0.pdf"]
    assert {row["status"] for row in ranking["rows"]} == {"done"}


def test_repeating_the_call_makes_no_job_and_no_call_and_matches_post_rankings(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    first = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    _added(client, first["position_id"], [CV_NEW])
    wait_until_settled(conn)
    calls, jobs = len(fake_llm.calls), _count(conn, "task_queue")

    again = _added(client, first["position_id"], [CV_NEW])
    wait_until_settled(conn)
    via_rankings = upload(client, POSTING, [CV_NEW])
    wait_until_settled(conn)

    assert len(fake_llm.calls) == calls
    assert _count(conn, "task_queue") == jobs
    assert _count(conn, "document") == 3 and len(_assessments(conn)) == 2
    by_position, by_posting = (
        _status(client, again["request_id"]),
        _status(client, via_rankings["request_id"]),
    )
    assert by_position["status"] == by_posting["status"] == "done"
    assert by_position["documents"] == by_posting["documents"]


def test_an_unknown_position_is_404_and_writes_nothing(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    response = add(client, UNKNOWN, [CV_NEW])

    assert response.status_code == 404
    assert response.json()["detail"] == "No such position"
    assert _count(conn, "document") == 0 and _count(conn, "ranking_request") == 0


def test_a_cv_stored_as_the_posting_is_rejected(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    first = upload(client, POSTING, [CV_OLD])

    response = add(client, first["position_id"], [CV_NEW, POSTING])

    assert response.status_code == 422
    assert response.json()["detail"] == "'add1.pdf' was already uploaded as a posting"
    assert _count(conn, "ranking_request") == 1  # only the first one
    assert _count(conn, "document") == 2  # the new CV was rolled back with the request


def test_validation_matches_post_rankings(
    client: TestClient, conn: psycopg.Connection[DictRow], monkeypatch: pytest.MonkeyPatch
) -> None:
    position_id = upload(client, POSTING, [CV_OLD])["position_id"]

    not_pdf = add(client, position_id, [CV_NEW, b"just some text"])
    assert not_pdf.status_code == 422 and "add1.pdf" in not_pdf.json()["detail"]
    assert client.post(f"/positions/{position_id}/cvs").status_code == 422  # no CV at all

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    too_big = add(client, position_id, [b"%PDF-1.7\n" + b"0" * (1024 * 1024)])
    assert too_big.status_code == 413
    assert _count(conn, "document") == 2 and _count(conn, "ranking_request") == 1


def test_a_stranded_position_is_set_up_and_its_cvs_judged(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    first = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    _forget_setup_and_judgements(conn)

    added = _added(client, first["position_id"], [CV_OLD])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done"]
    assert _status(client, added["request_id"])["status"] == "done"


def test_a_failed_posting_is_ingested_again_as_on_reupload(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    first = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    conn.execute("UPDATE document SET status = 'failed' WHERE kind = 'posting'")

    added = _added(client, first["position_id"], [CV_NEW])
    wait_until_settled(conn)

    state = _status(client, added["request_id"])
    assert state["status"] == "done"
    assert state["documents"][0]["kind"] == "posting"
    assert state["documents"][0]["status"] == "extracted"


def test_a_mixed_batch_of_known_and_new_cvs_judges_only_the_new_one(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    first = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    judged = _judge_calls(fake_llm)

    mixed = _added(client, first["position_id"], [CV_OLD, CV_NEW, CV_SCAN])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done", "done"]
    assert _judge_calls(fake_llm) == judged + 1  # only the new CV is judged
    state = _status(client, mixed["request_id"])
    assert state["status"] == "done"
    assert state["documents"][0]["kind"] == "posting"
    assert sorted(d["status"] for d in state["documents"]) == [
        "extracted",
        "parsed",
        "parsed",
        "rejected",
    ]
