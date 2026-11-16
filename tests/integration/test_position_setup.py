"""Position setup through the real worker loop, with a scripted model."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf, make_scan_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.db import task_queue
from ats.db.pool import create_pool
from ats.db.task_queue import Job
from ats.llm.fake import FakeLLMClient
from ats.pipeline.requirements import RequirementList
from ats.services.requirements import POSITION_SETUP_JOB
from ats.worker.ingest import ingest
from ats.worker.position_setup import position_setup
from integration.test_ingest import CV_ENGLISH, CV_LATIN, upload, wait_until_settled
from integration.test_worker import wait_for

pytestmark = pytest.mark.integration

POSTING = make_pdf(
    "Senior Java developer\nRequirements: Java, 3 years of experience in Java,\n"
    "a degree and 3 years of experience, Docker is a plus.\n" * 3
)

SCRIPTED = RequirementList.model_validate_json(
    json.dumps(
        {
            "requirements": [
                {"id": 1, "text": "Java", "kind": "mandatory", "weight": 3}
                | {"min_months": None, "parent": None},
                {"id": 2, "text": "3 years of experience in Java", "kind": "mandatory"}
                | {"weight": 3, "min_months": 36, "parent": 1},
                {"id": 3, "text": "A degree", "kind": "mandatory", "weight": 1}
                | {"min_months": None, "parent": None},
                {"id": 4, "text": "3 years of experience", "kind": "mandatory"}
                | {"weight": 1, "min_months": 36, "parent": None},
                {"id": 5, "text": "Docker", "kind": "nice_to_have", "weight": 1}
                | {"min_months": None, "parent": None},
            ]
        }
    )
)


def scripted(fake: FakeLLMClient) -> None:
    fake.responder = lambda _request, _schema: SCRIPTED


def test_uploading_a_posting_creates_unconfirmed_requirements(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    scripted(fake_llm)

    upload(client, POSTING, [CV_ENGLISH])
    wait_until_settled(conn)

    position = conn.execute("SELECT id, rubric_status, rubric_version FROM job_position").fetchone()
    assert position is not None
    assert (position["rubric_status"], position["rubric_version"]) == ("unconfirmed", 1)
    rows = conn.execute(
        "SELECT id, parent_id, ord, text, kind, weight, min_months, rubric_version "
        "FROM requirement WHERE position_id = %s ORDER BY ord",
        (position["id"],),
    ).fetchall()
    assert [row["text"] for row in rows] == [
        "Java",
        "3 years of experience in Java",
        "A degree",
        "3 years of experience",
        "Docker",
    ]
    java, java_years, degree, years, docker = rows
    assert java_years["parent_id"] == java["id"]
    assert java_years["min_months"] == 36
    # "A degree and 3 years of experience" are two rows and neither refines the other.
    assert degree["parent_id"] is None and years["parent_id"] is None
    assert docker["kind"] == "nice_to_have"
    assert {row["rubric_version"] for row in rows} == {1}
    assert len(fake_llm.calls) == 1
    assert "Senior Java developer" in fake_llm.calls[0].user


def test_the_same_posting_again_skips_setup_entirely(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    scripted(fake_llm)
    upload(client, POSTING, [CV_ENGLISH])
    wait_until_settled(conn)

    upload(client, POSTING, [CV_LATIN])
    wait_until_settled(conn)

    assert len(fake_llm.calls) == 1
    assert conn.execute("SELECT count(*) AS n FROM requirement").fetchone() == {"n": 5}
    setups = conn.execute(
        "SELECT count(*) AS n FROM task_queue WHERE job_type = %s", (POSITION_SETUP_JOB,)
    ).fetchone()
    assert setups == {"n": 1}


def test_a_scanned_posting_gets_no_setup_job(
    client: TestClient, worker: ConnectionPool, conn: psycopg.Connection[DictRow]
) -> None:
    upload(client, make_scan_pdf(), [CV_ENGLISH])
    wait_until_settled(conn)

    assert conn.execute(
        "SELECT count(*) AS n FROM task_queue WHERE job_type = %s", (POSITION_SETUP_JOB,)
    ).fetchone() == {"n": 0}


def test_running_the_job_twice_extracts_once(
    worker: ConnectionPool, conn: psycopg.Connection[DictRow], fake_llm: FakeLLMClient
) -> None:
    """A redelivered job, after its worker died past the commit, must not pay again."""
    scripted(fake_llm)
    position = conn.execute(
        "INSERT INTO job_position (source_sha256, posting_text) VALUES ('abc', 'Requires Java') "
        "RETURNING id"
    ).fetchone()
    assert position is not None
    job = Job(
        id=1,
        job_type=POSITION_SETUP_JOB,
        payload={"position_id": str(position["id"])},
        attempts=1,
        max_attempts=3,
    )

    position_setup(job, worker)
    position_setup(job, worker)

    assert len(fake_llm.calls) == 1
    assert conn.execute("SELECT count(*) AS n FROM requirement").fetchone() == {"n": 5}


def test_a_failing_model_leaves_no_requirements_and_a_failed_job(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    def broken(*_args: object) -> RequirementList:
        raise RuntimeError("quota exhausted")

    fake_llm.responder = broken

    upload(client, POSTING, [CV_ENGLISH])
    wait_for(
        lambda: (
            conn.execute(
                "SELECT 1 FROM task_queue WHERE job_type = %s AND status = 'failed'",
                (POSITION_SETUP_JOB,),
            ).fetchone()
            is not None
        )
    )

    job = conn.execute(
        "SELECT attempts, error FROM task_queue WHERE job_type = %s", (POSITION_SETUP_JOB,)
    ).fetchone()
    assert job is not None
    assert job["attempts"] == 3
    assert "quota exhausted" in job["error"]
    assert conn.execute("SELECT count(*) AS n FROM requirement").fetchone() == {"n": 0}


def test_uploading_the_posting_again_retries_a_failed_setup(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    fake_llm: FakeLLMClient,
) -> None:
    def broken(*_args: object) -> RequirementList:
        raise RuntimeError("model overloaded")

    fake_llm.responder = broken
    upload(client, POSTING, [CV_ENGLISH])
    wait_for(
        lambda: (
            conn.execute(
                "SELECT 1 FROM task_queue WHERE job_type = %s AND status = 'failed'",
                (POSITION_SETUP_JOB,),
            ).fetchone()
            is not None
        )
    )
    assert conn.execute("SELECT count(*) AS n FROM requirement").fetchone() == {"n": 0}

    scripted(fake_llm)  # the model recovers
    upload(client, POSTING, [CV_LATIN])
    wait_until_settled(conn)

    assert conn.execute("SELECT count(*) AS n FROM requirement").fetchone() == {"n": 5}
    jobs = conn.execute(
        "SELECT status FROM task_queue WHERE job_type = %s", (POSITION_SETUP_JOB,)
    ).fetchall()
    assert jobs == [{"status": "done"}]  # the same job row, not a second one


def test_ingesting_a_new_posting_enqueues_exactly_one_setup_job_with_the_text_stored(
    client: TestClient, test_db_url: str, conn: psycopg.Connection[DictRow]
) -> None:
    """Only the real ingest handler runs: no worker loop, no model.

    The job must exist by the time the posting text does, because both are written in one
    transaction. This is what a stale worker (one started before the enqueue existed) lacks.
    """
    upload(client, POSTING, [CV_ENGLISH])
    setup_jobs = "SELECT payload, dedup_key FROM task_queue WHERE job_type = %s"
    assert conn.execute(setup_jobs, (POSITION_SETUP_JOB,)).fetchall() == []  # nothing before ingest

    pool = create_pool(test_db_url, 2)
    pool.open(wait=True, timeout=10)
    try:
        with pool.connection() as queue:
            while (job := task_queue.claim(queue)) is not None:
                if job.job_type == "ingest":
                    ingest(job, pool)
    finally:
        pool.close()

    position = conn.execute("SELECT id, posting_text FROM job_position").fetchone()
    assert position is not None and "Senior Java developer" in position["posting_text"]
    jobs = conn.execute(setup_jobs, (POSITION_SETUP_JOB,)).fetchall()
    assert jobs == [
        {
            "payload": {"position_id": str(position["id"])},
            "dedup_key": f"{POSITION_SETUP_JOB}:{position['id']}",
        }
    ]
