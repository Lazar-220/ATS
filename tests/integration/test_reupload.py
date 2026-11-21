"""Uploading files the system already knows: every case is accepted and ends in a sensible state.

Fake model and synthetic PDFs only. The legacy states are built by settling a normal upload and
then deleting what an older version of the code never wrote, so the tests need no old data.
"""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf, make_scan_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.llm.fake import FakeLLMClient
from integration.test_ingest import upload, wait_until_settled

pytestmark = pytest.mark.integration

POSTING = make_pdf("Senior Python developer, Belgrade\n" + "Zahtevi: pet godina iskustva. " * 6)
CV_OLD = make_pdf("Led a team of eight people at a bank, 2019-2023.\n" * 6)
CV_NEW = make_pdf("Built payment services in Python for six years.\n" * 6)
CV_SCAN = make_scan_pdf()


def _status(client: TestClient, request_id: str) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"/rankings/{request_id}").json()
    return body


def _assessments(conn: psycopg.Connection[DictRow]) -> list[dict[str, Any]]:
    return conn.execute("SELECT candidate_id, status FROM assessment").fetchall()


def _judge_calls(fake: FakeLLMClient) -> int:
    return sum(1 for call in fake.calls if call.prompt_version.startswith("judge"))


def _forget_setup_and_judgements(conn: psycopg.Connection[DictRow]) -> None:
    """A position made before requirement extraction existed: posting text, no requirements and
    no setup job. Its CVs were parsed and waited forever."""
    conn.execute("DELETE FROM assessment")
    conn.execute("DELETE FROM task_queue WHERE job_type IN ('judge', 'position_setup')")
    conn.execute("DELETE FROM requirement")


def test_a_posting_that_was_extracted_but_never_set_up_is_set_up_on_reupload(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
) -> None:
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    _forget_setup_and_judgements(conn)

    again = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done"]
    assert _status(client, again["request_id"])["status"] == "done"


def test_a_cv_that_stopped_at_extracted_is_parsed_and_judged_on_reupload(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
) -> None:
    """Documents ingested before CV parsing existed stay `extracted` and no job is left."""
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    conn.execute("DELETE FROM assessment")
    conn.execute("DELETE FROM task_queue WHERE job_type IN ('judge', 'ingest')")
    conn.execute("UPDATE request_candidate SET candidate_id = NULL")
    conn.execute(
        "UPDATE document SET status = 'extracted', candidate_id = NULL, masked_text = NULL, "
        "parsed_json = NULL, mask_spans = NULL WHERE kind = 'cv'"
    )

    again = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    document = conn.execute("SELECT status FROM document WHERE kind = 'cv'").fetchone()
    assert document is not None and document["status"] == "parsed"
    assert [row["status"] for row in _assessments(conn)] == ["done"]
    assert _status(client, again["request_id"])["status"] == "done"


def test_a_parsed_cv_whose_assessment_is_missing_is_judged_again_on_reupload(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
) -> None:
    """The judge job's key is unique for all time, so a finished job with no result behind it
    must be put back in the queue by the upload, not skipped."""
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    conn.execute("DELETE FROM assessment")

    again = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done"]
    judge_rows = conn.execute("SELECT status FROM task_queue WHERE job_type = 'judge'").fetchall()
    assert [row["status"] for row in judge_rows] == ["done"]  # one row, reused
    assert _status(client, again["request_id"])["status"] == "done"


def test_reuploading_a_finished_pair_reuses_the_result_with_no_new_call(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    calls = len(fake_llm.calls)
    jobs = conn.execute("SELECT count(*) AS n FROM task_queue").fetchone()

    again = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    assert len(fake_llm.calls) == calls
    assert len(_assessments(conn)) == 1
    assert conn.execute("SELECT count(*) AS n FROM task_queue").fetchone() == jobs
    assert _status(client, again["request_id"])["status"] == "done"


def test_reuploading_a_failed_cv_retries_it_to_the_end(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
) -> None:
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    # What a CV that ran out of attempts looks like: no candidate, no assessment, no live job.
    conn.execute("DELETE FROM assessment")
    conn.execute("DELETE FROM task_queue WHERE job_type IN ('judge', 'ingest')")
    conn.execute("UPDATE request_candidate SET candidate_id = NULL")
    conn.execute(
        "UPDATE document SET status = 'failed', status_message = 'Processing failed', "
        "candidate_id = NULL, masked_text = NULL, parsed_json = NULL, mask_spans = NULL "
        "WHERE kind = 'cv'"
    )

    again = upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done"]
    assert _status(client, again["request_id"])["status"] == "done"


def test_reuploading_a_scan_is_accepted_and_shows_the_stored_message_again(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    first = upload(client, POSTING, [CV_SCAN])
    wait_until_settled(conn)
    message = next(
        doc["message"]
        for doc in _status(client, first["request_id"])["documents"]
        if doc["kind"] == "cv"
    )
    assert message
    calls = len(fake_llm.calls)
    jobs = conn.execute("SELECT count(*) AS n FROM task_queue").fetchone()

    again = upload(client, POSTING, [CV_SCAN])
    wait_until_settled(conn)

    documents = _status(client, again["request_id"])["documents"]
    cv = next(doc for doc in documents if doc["kind"] == "cv")
    assert (cv["status"], cv["message"]) == ("rejected", message)
    assert len(fake_llm.calls) == calls
    assert conn.execute("SELECT count(*) AS n FROM task_queue").fetchone() == jobs


def test_a_batch_of_a_known_cv_and_a_new_one_ends_with_both_assessed(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    judged = _judge_calls(fake_llm)

    mixed = upload(client, POSTING, [CV_OLD, CV_NEW, CV_SCAN])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done", "done"]
    assert _judge_calls(fake_llm) == judged + 1  # only the new CV is judged
    state = _status(client, mixed["request_id"])
    assert state["status"] == "done"
    assert sorted(doc["status"] for doc in state["documents"]) == [
        "extracted",
        "parsed",
        "parsed",
        "rejected",
    ]


def test_a_batch_on_a_stranded_position_with_known_and_new_cvs_is_processed_whole(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
) -> None:
    upload(client, POSTING, [CV_OLD])
    wait_until_settled(conn)
    _forget_setup_and_judgements(conn)

    mixed = upload(client, POSTING, [CV_OLD, CV_NEW])
    wait_until_settled(conn)

    assert [row["status"] for row in _assessments(conn)] == ["done", "done"]
    assert _status(client, mixed["request_id"])["status"] == "done"
