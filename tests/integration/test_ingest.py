"""Upload through the API, let the real worker loop run, then read the database.

Nothing calls the handler directly: the point is that results appear without a further call.
"""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf, make_scan_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.db import task_queue
from ats.worker import ingest as ingest_module
from integration.test_worker import wait_for

pytestmark = pytest.mark.integration

POSTING = make_pdf("Senior Python developer, Belgrade\n" + "Zahtevi: pet godina iskustva. " * 6)
CV_LATIN = make_pdf("Vođenje tima od osam ljudi u banci, 2019-2023.\n" * 6)
CV_CYRILLIC = make_pdf("Вођење тима од осам људи у банци, 2019-2023.\n" * 6)
CV_ENGLISH = make_pdf("Led a team of eight people at a bank, 2019-2023.\n" * 6)
CV_SCAN = make_scan_pdf()


def upload(client: TestClient, posting: bytes, cvs: list[bytes]) -> Any:
    files = [("posting", ("posting.pdf", posting, "application/pdf"))]
    files += [("cvs", (f"cv{i}.pdf", cv, "application/pdf")) for i, cv in enumerate(cvs)]
    response = client.post("/rankings", files=files)
    assert response.status_code == 202
    return response.json()


def wait_until_settled(conn: psycopg.Connection[DictRow]) -> None:
    """Every document is out of `uploaded` and the queue is idle (a job is marked done just
    after its document is written, so the document alone is not enough)."""

    def settled() -> bool:
        row = conn.execute(
            "SELECT (SELECT count(*) FROM document WHERE status = 'uploaded') AS waiting, "
            "(SELECT count(*) FROM task_queue WHERE status IN ('queued', 'running')) AS busy"
        ).fetchone()
        return row is not None and row["waiting"] == 0 and row["busy"] == 0

    wait_for(settled)


def documents_by_sha(conn: psycopg.Connection[DictRow]) -> dict[str, dict[str, Any]]:
    rows = conn.execute("SELECT * FROM document").fetchall()
    return {row["sha256"]: row for row in rows}


def test_three_cvs_get_clean_text_with_the_right_language_and_script(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    upload(client, POSTING, [CV_LATIN, CV_CYRILLIC, CV_ENGLISH])
    wait_until_settled(conn)

    cvs = conn.execute(
        "SELECT filename, status, raw_text, lang, script FROM document "
        "WHERE kind = 'cv' ORDER BY filename"
    ).fetchall()
    latin, cyrillic, english = cvs
    assert (latin["status"], latin["lang"], latin["script"]) == ("extracted", "sr", "latin")
    assert "Vođenje tima od osam ljudi" in latin["raw_text"]
    assert (cyrillic["status"], cyrillic["lang"], cyrillic["script"]) == (
        "extracted",
        "sr",
        "cyrillic",
    )
    # Stored in the original script; only the lexical comparison transliterates.
    assert "Вођење тима од осам људи" in cyrillic["raw_text"]
    assert (english["status"], english["lang"], english["script"]) == ("extracted", "en", "latin")
    assert "Led a team of eight people" in english["raw_text"]


def test_the_posting_text_lands_on_the_position(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    upload(client, POSTING, [CV_ENGLISH])
    wait_until_settled(conn)

    position = conn.execute("SELECT posting_text FROM job_position").fetchone()
    assert position is not None
    assert "Senior Python developer" in position["posting_text"]


def test_a_scanned_cv_is_rejected_and_the_others_still_finish(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    upload(client, POSTING, [CV_SCAN, CV_ENGLISH])
    wait_until_settled(conn)

    rows = conn.execute(
        "SELECT status, status_message, raw_text FROM document WHERE kind = 'cv' ORDER BY status"
    ).fetchall()
    extracted, rejected = rows
    assert extracted["status"] == "extracted"
    assert rejected["status"] == "rejected"
    assert "scan" in rejected["status_message"]
    assert rejected["raw_text"] is None
    jobs = conn.execute("SELECT DISTINCT status FROM task_queue").fetchall()
    assert [job["status"] for job in jobs] == ["done"]


def test_a_redelivered_job_does_not_redo_finished_work(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    upload(client, POSTING, [CV_ENGLISH])
    wait_until_settled(conn)
    conn.execute("UPDATE document SET raw_text = 'edited', status = 'parsed' WHERE kind = 'cv'")
    cv = conn.execute("SELECT id FROM document WHERE kind = 'cv'").fetchone()
    assert cv is not None

    with worker.connection() as queue:  # the queue expects tuple rows, not `conn`'s dicts
        task_queue.enqueue(queue, "ingest", {"document_id": str(cv["id"])}, dedup_key="again")
    wait_for(
        lambda: (
            (
                conn.execute(
                    "SELECT count(*) AS n FROM task_queue WHERE status IN ('queued', 'running')"
                ).fetchone()
                or {"n": 1}
            )["n"]
            == 0
        )
    )

    after = conn.execute("SELECT raw_text, status FROM document WHERE kind = 'cv'").fetchone()
    assert after is not None
    assert (after["raw_text"], after["status"]) == ("edited", "parsed")


def test_unexpected_errors_fail_the_document_and_a_reupload_recovers(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_extract = ingest_module.extract_text

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(ingest_module, "extract_text", broken)
    upload(client, POSTING, [CV_ENGLISH])
    wait_for(
        lambda: (
            conn.execute("SELECT 1 FROM document WHERE status = 'failed'").fetchone() is not None
            and conn.execute("SELECT 1 FROM task_queue WHERE status = 'running'").fetchone() is None
        )
    )
    failed = conn.execute("SELECT status_message FROM document WHERE kind = 'cv'").fetchone()
    assert failed is not None
    assert "Upload the file again" in failed["status_message"]
    job = conn.execute(
        "SELECT attempts, status, error FROM task_queue WHERE payload->>'document_id' = "
        "(SELECT id::text FROM document WHERE kind = 'cv')"
    ).fetchone()
    assert job is not None
    assert (job["attempts"], job["status"]) == (3, "failed")
    assert "disk on fire" in job["error"]

    monkeypatch.setattr(ingest_module, "extract_text", real_extract)
    upload(client, POSTING, [CV_ENGLISH])
    wait_until_settled(conn)

    recovered = conn.execute("SELECT status, raw_text FROM document WHERE kind = 'cv'").fetchone()
    assert recovered is not None
    assert recovered["status"] == "extracted"
    assert "Led a team" in recovered["raw_text"]


def test_status_endpoint_shows_done_and_the_scan_message(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    accepted = upload(client, POSTING, [CV_SCAN, CV_ENGLISH])
    wait_until_settled(conn)

    body = client.get(f"/rankings/{accepted['request_id']}").json()

    assert body["status"] == "done"
    by_name = {d["filename"]: d for d in body["documents"]}
    assert by_name["cv0.pdf"]["status"] == "rejected"
    assert "looks like a scan" in by_name["cv0.pdf"]["message"]
    assert by_name["cv1.pdf"]["status"] == "extracted"
    assert by_name["cv1.pdf"]["message"] is None
