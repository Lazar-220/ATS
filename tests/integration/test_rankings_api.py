import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from psycopg import sql
from psycopg.rows import DictRow

from ats.api.main import app
from ats.settings import get_settings

pytestmark = pytest.mark.integration

POSTING = make_pdf("Senior Python developer\n" + "Requirements: five years of Python. " * 5)
CV_A = make_pdf("Ana Anić\n" + "Vođenje tima od osam ljudi u banci. " * 5)
CV_B = make_pdf("Bojan Bojić\n" + "Led a team of eight people at a bank. " * 5)


@pytest.fixture
def uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    return tmp_path


@pytest.fixture
def client(uploads: Path, conn: psycopg.Connection[DictRow]) -> Iterator[TestClient]:
    # `conn` empties the tables first; the lifespan then opens the API's own pool.
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def post(
    client: TestClient, posting: bytes, cvs: list[bytes], names: list[str] | None = None
) -> Any:
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("posting", ("posting.pdf", posting, "application/pdf"))
    ]
    for index, cv in enumerate(cvs):
        name = names[index] if names else f"cv{index}.pdf"
        files.append(("cvs", (name, cv, "application/pdf")))
    return client.post("/rankings", files=files)


def count(conn: psycopg.Connection[DictRow], table: str) -> int:
    query = sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
    row = conn.execute(query).fetchone()
    assert row is not None
    return int(row["n"])


def ingest_jobs(conn: psycopg.Connection[DictRow]) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT payload, status, dedup_key FROM task_queue WHERE job_type = 'ingest' ORDER BY id"
    ).fetchall()


def test_post_returns_202_and_creates_rows_files_and_jobs(
    client: TestClient, conn: psycopg.Connection[DictRow], uploads: Path
) -> None:
    response = post(client, POSTING, [CV_A, CV_B])

    assert response.status_code == 202
    body = response.json()
    position = conn.execute("SELECT * FROM job_position").fetchone()
    assert position is not None
    assert str(position["id"]) == body["position_id"]
    assert position["rubric_status"] == "unconfirmed"
    assert position["rubric_version"] == 1
    assert position["source_sha256"] == hashlib.sha256(POSTING).hexdigest()

    request = conn.execute("SELECT id, type, status FROM ranking_request").fetchone()
    assert request is not None
    assert str(request["id"]) == body["request_id"]
    assert (request["type"], request["status"]) == ("submit", "queued")

    assert count(conn, "document") == 3
    assert count(conn, "request_candidate") == 2
    assert len(ingest_jobs(conn)) == 3
    for pdf in (POSTING, CV_A, CV_B):
        stored = uploads / f"{hashlib.sha256(pdf).hexdigest()}.pdf"
        assert stored.read_bytes() == pdf
    documents = conn.execute("SELECT kind, storage_path FROM document ORDER BY kind").fetchall()
    assert [d["kind"] for d in documents] == ["cv", "cv", "posting"]
    assert all(not Path(d["storage_path"]).is_absolute() for d in documents)


def test_same_cv_twice_creates_one_document_and_one_job(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    first = post(client, POSTING, [CV_A])
    second = post(client, POSTING, [CV_A, CV_A])

    assert first.status_code == second.status_code == 202
    assert count(conn, "document") == 2  # the posting and the CV
    assert len(ingest_jobs(conn)) == 2
    # Each request still lists the CV, so both can show their own results.
    assert count(conn, "ranking_request") == 2
    assert count(conn, "request_candidate") == 2


def test_same_posting_twice_resolves_to_the_same_position(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    first = post(client, POSTING, [CV_A]).json()
    second = post(client, POSTING, [CV_B]).json()

    assert first["position_id"] == second["position_id"]
    assert first["request_id"] != second["request_id"]
    assert count(conn, "job_position") == 1


def test_a_failed_document_is_ingested_again_on_reupload(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    post(client, POSTING, [CV_A])
    conn.execute("UPDATE document SET status = 'failed' WHERE kind = 'cv'")

    post(client, POSTING, [CV_A])

    cv = conn.execute("SELECT status FROM document WHERE kind = 'cv'").fetchone()
    assert cv is not None
    assert cv["status"] == "uploaded"
    assert len(ingest_jobs(conn)) == 3  # posting, CV, and the CV again
    assert len({job["dedup_key"] for job in ingest_jobs(conn)}) == 3


def test_a_rejected_document_is_not_ingested_again(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    post(client, POSTING, [CV_A])
    conn.execute(
        "UPDATE document SET status = 'rejected', status_message = 'scan' WHERE kind = 'cv'"
    )

    post(client, POSTING, [CV_A])

    cv = conn.execute("SELECT status FROM document WHERE kind = 'cv'").fetchone()
    assert cv is not None
    assert cv["status"] == "rejected"
    assert len(ingest_jobs(conn)) == 2


def test_a_non_pdf_is_rejected_before_anything_is_stored(
    client: TestClient, conn: psycopg.Connection[DictRow], uploads: Path
) -> None:
    response = post(client, POSTING, [CV_A, b"just some text"], names=["a.pdf", "notes.pdf"])

    assert response.status_code == 422
    assert "notes.pdf" in response.json()["detail"]
    assert count(conn, "document") == 0
    assert count(conn, "ranking_request") == 0
    assert list(uploads.iterdir()) == []


def test_an_oversized_file_is_rejected(
    client: TestClient, conn: psycopg.Connection[DictRow], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)

    response = post(client, POSTING, [big])

    assert response.status_code == 413
    assert count(conn, "document") == 0


def test_the_same_file_as_posting_and_cv_is_rejected(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    response = post(client, POSTING, [POSTING])

    assert response.status_code == 422
    assert count(conn, "ranking_request") == 0


def test_a_cv_already_stored_as_a_posting_is_rejected(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    post(client, POSTING, [CV_A])

    response = post(client, CV_A, [CV_B])

    assert response.status_code == 422
    assert "already uploaded as a cv" in response.json()["detail"]
    assert count(conn, "ranking_request") == 1  # only the first one


def test_missing_cvs_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/rankings", files=[("posting", ("p.pdf", POSTING, "application/pdf"))])
    assert response.status_code == 422


def test_status_of_a_new_request_is_queued_with_the_posting_first(client: TestClient) -> None:
    accepted = post(client, POSTING, [CV_B, CV_A], names=["b.pdf", "a.pdf"]).json()

    response = client.get(f"/rankings/{accepted['request_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["position_id"] == accepted["position_id"]
    assert [(d["kind"], d["filename"], d["status"]) for d in body["documents"]] == [
        ("posting", "posting.pdf", "uploaded"),
        ("cv", "a.pdf", "uploaded"),
        ("cv", "b.pdf", "uploaded"),
    ]
    assert all(d["message"] is None for d in body["documents"])


def test_status_of_an_unknown_request_is_404(client: TestClient) -> None:
    response = client.get("/rankings/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_status_with_a_malformed_id_is_a_validation_error(client: TestClient) -> None:
    assert client.get("/rankings/not-a-uuid").status_code == 422


def test_status_is_running_while_some_documents_are_still_waiting(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    accepted = post(client, POSTING, [CV_A, CV_B]).json()
    conn.execute("UPDATE document SET status = 'extracted' WHERE kind = 'posting'")

    status = client.get(f"/rankings/{accepted['request_id']}").json()["status"]
    assert status == "running"


def test_status_is_failed_when_the_posting_is_rejected(
    client: TestClient, conn: psycopg.Connection[DictRow]
) -> None:
    accepted = post(client, POSTING, [CV_A]).json()
    conn.execute("UPDATE document SET status = 'extracted' WHERE kind = 'cv'")
    conn.execute(
        "UPDATE document SET status = 'rejected', status_message = 'scan' WHERE kind = 'posting'"
    )

    body = client.get(f"/rankings/{accepted['request_id']}").json()
    assert body["status"] == "failed"
    assert body["documents"][0]["message"] == "scan"
