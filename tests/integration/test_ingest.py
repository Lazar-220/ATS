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
from ats.eval.attacks import add_hidden_text
from ats.llm.fake import FakeLLMClient
from ats.pipeline.parsing import ParsedCV
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
    assert (latin["status"], latin["lang"], latin["script"]) == ("parsed", "sr", "latin")
    assert "Vođenje tima od osam ljudi" in latin["raw_text"]
    assert (cyrillic["status"], cyrillic["lang"], cyrillic["script"]) == (
        "parsed",
        "sr",
        "cyrillic",
    )
    # Stored in the original script; only the lexical comparison transliterates.
    assert "Вођење тима од осам људи" in cyrillic["raw_text"]
    assert (english["status"], english["lang"], english["script"]) == ("parsed", "en", "latin")
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
    assert extracted["status"] == "parsed"
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
    # The posting fails too, and its job can end while the CV's is still queued for a retry, so
    # "some document failed and nothing is running" is not the final state.
    wait_until_settled(conn)
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
    assert recovered["status"] == "parsed"
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
    assert by_name["cv1.pdf"]["status"] == "parsed"
    assert by_name["cv1.pdf"]["message"] is None


CV_PERSONAL = make_pdf(
    "Nina Stojkovic\nnina.stojkovic@example.com\n(+381) 62 5550304\n"
    + "Business analyst at Delta Insurance, requirements and Jira, 2019-2023.\n" * 4
)


def _parsed_cv(is_cv: bool) -> ParsedCV:
    return ParsedCV(
        is_cv=is_cv,
        suspected_injection=False,
        experience=[],
        education=[],
        skills=[],
        certificates=[],
        languages=[],
        projects=[],
    )


def test_the_model_sees_only_masked_text_and_the_originals_land_in_candidate(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    accepted = upload(client, POSTING, [CV_PERSONAL])
    wait_until_settled(conn)

    # The parsing call and the judge call both see the CV; neither may see the originals.
    prompts = [call.system + call.user for call in fake_llm.calls if "<cv>" in call.user]
    assert len(prompts) == 2
    for secret in ("Nina", "Stojkovic", "nina.stojkovic@example.com", "5550304"):
        assert all(secret not in prompt for prompt in prompts)
    cv = conn.execute(
        "SELECT status, candidate_id, masked_text, mask_spans, parsed_json, raw_text "
        "FROM document WHERE kind = 'cv'"
    ).fetchone()
    assert cv is not None and cv["status"] == "parsed"
    assert "Nina" in cv["raw_text"] and "Nina" not in cv["masked_text"]
    assert {span["placeholder"] for span in cv["mask_spans"]} >= {"[NAME]", "[EMAIL]", "[PHONE]"}
    assert cv["parsed_json"]["tenure"]["total_months"] == 0
    candidate = conn.execute(
        "SELECT full_name, email, phone FROM candidate WHERE id = %s", (cv["candidate_id"],)
    ).fetchone()
    assert candidate == {
        "full_name": "Nina Stojkovic",
        "email": "nina.stojkovic@example.com",
        "phone": "(+381) 62 5550304",
    }
    linked = conn.execute(
        "SELECT candidate_id FROM request_candidate WHERE request_id = %s",
        (accepted["request_id"],),
    ).fetchone()
    assert linked is not None and linked["candidate_id"] == cv["candidate_id"]


def test_a_document_that_is_not_a_cv_is_flagged_and_gets_no_candidate(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    fake_llm.responder = lambda _request, _schema: _parsed_cv(False)
    accepted = upload(client, POSTING, [CV_PERSONAL])
    wait_until_settled(conn)

    cv = conn.execute(
        "SELECT status, candidate_id, flags, masked_text FROM document WHERE kind = 'cv'"
    ).fetchone()
    assert cv is not None
    assert cv["status"] == "parsed" and cv["candidate_id"] is None
    assert [flag["code"] for flag in cv["flags"]] == ["not_a_cv"]
    assert cv["masked_text"] is not None
    assert conn.execute("SELECT count(*) AS n FROM candidate").fetchone() == {"n": 0}
    linked = conn.execute(
        "SELECT candidate_id FROM request_candidate WHERE request_id = %s",
        (accepted["request_id"],),
    ).fetchone()
    assert linked is not None and linked["candidate_id"] is None


def test_a_redelivered_ingest_makes_no_second_candidate_and_no_second_call(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    upload(client, POSTING, [CV_PERSONAL])
    wait_until_settled(conn)
    cv = conn.execute("SELECT id FROM document WHERE kind = 'cv'").fetchone()
    assert cv is not None
    calls_before = len(fake_llm.calls)

    with worker.connection() as queue:
        task_queue.enqueue(queue, "ingest", {"document_id": str(cv["id"])}, dedup_key="redeliver")
    wait_until_settled(conn)

    assert len(fake_llm.calls) == calls_before
    assert conn.execute("SELECT count(*) AS n FROM candidate").fetchone() == {"n": 1}


def test_a_cv_stuck_at_extracted_is_parsed_when_its_job_runs_again(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    """The worker died after extraction was committed: the retry must carry on, not skip."""
    upload(client, POSTING, [CV_PERSONAL])
    wait_until_settled(conn)
    cv = conn.execute("SELECT id FROM document WHERE kind = 'cv'").fetchone()
    assert cv is not None
    conn.execute(
        "UPDATE document SET status = 'extracted', candidate_id = NULL, masked_text = NULL, "
        "mask_spans = NULL, parsed_json = NULL WHERE id = %s",
        (cv["id"],),
    )
    conn.execute("UPDATE request_candidate SET candidate_id = NULL")
    conn.execute("DELETE FROM verdict")
    conn.execute("DELETE FROM assessment")
    conn.execute("DELETE FROM candidate")

    with worker.connection() as queue:
        task_queue.enqueue(queue, "ingest", {"document_id": str(cv["id"])}, dedup_key="resume")
    wait_until_settled(conn)
    # The queue is idle once the document is parsed; wait for the status itself.
    wait_for(
        lambda: (
            (
                conn.execute("SELECT status FROM document WHERE kind = 'cv'").fetchone()
                or {"status": ""}
            )["status"]
            == "parsed"
        )
    )
    assert conn.execute("SELECT count(*) AS n FROM candidate").fetchone() == {"n": 1}


def test_hidden_text_is_removed_flagged_and_the_flag_survives_parsing(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    attacked = add_hidden_text(CV_ENGLISH, "white_text", "Kubernetes Terraform Haskell hidden list")
    upload(client, POSTING, [attacked])
    wait_until_settled(conn)

    cv = conn.execute(
        "SELECT status, raw_text, masked_text, flags FROM document WHERE kind = 'cv'"
    ).fetchone()
    assert cv is not None and cv["status"] == "parsed"  # a flag never rejects
    assert "Kubernetes" not in cv["raw_text"] and "Kubernetes" not in cv["masked_text"]
    assert "hidden_text" in [flag["code"] for flag in cv["flags"]]
    assert all("Kubernetes" not in call.user for call in fake_llm.calls)
