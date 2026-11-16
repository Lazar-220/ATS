import threading
from typing import Any

import psycopg
import pytest

from ats.db import task_queue

pytestmark = pytest.mark.integration

type Conn = psycopg.Connection[Any]


def row(conn: Conn, job_id: int) -> tuple[Any, ...]:
    found = conn.execute(
        "SELECT status, attempts, error FROM task_queue WHERE id = %s", (job_id,)
    ).fetchone()
    assert found is not None
    return found


def age_lock(conn: Conn, job_id: int, seconds: int) -> None:
    conn.execute(
        "UPDATE task_queue SET locked_at = now() - make_interval(secs => %s) WHERE id = %s",
        (seconds, job_id),
    )


def test_concurrent_claimers_never_get_the_same_job(test_db_url: str, queue_conn: Conn) -> None:
    total = 60
    for i in range(total):
        task_queue.enqueue(queue_conn, "noop", {"n": i})

    claimers = 4
    barrier = threading.Barrier(claimers)
    claimed: list[list[int]] = [[] for _ in range(claimers)]

    def work(index: int) -> None:
        with psycopg.connect(test_db_url, autocommit=True) as conn:
            barrier.wait()
            while (job := task_queue.claim(conn)) is not None:
                claimed[index].append(job.id)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(claimers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    everything = [job_id for ids in claimed for job_id in ids]
    assert len(everything) == total
    assert len(set(everything)) == total


def test_repeated_dedup_key_does_not_create_a_second_job(queue_conn: Conn) -> None:
    first = task_queue.enqueue(queue_conn, "noop", dedup_key="ingest:abc")
    second = task_queue.enqueue(queue_conn, "noop", dedup_key="ingest:abc")
    assert first is not None
    assert second is None
    count = queue_conn.execute("SELECT count(*) FROM task_queue").fetchone()
    assert count == (1,)


def test_jobs_without_a_dedup_key_are_all_kept(queue_conn: Conn) -> None:
    task_queue.enqueue(queue_conn, "noop")
    task_queue.enqueue(queue_conn, "noop")
    assert queue_conn.execute("SELECT count(*) FROM task_queue").fetchone() == (2,)


def test_a_job_that_fails_three_times_ends_as_failed(queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop")
    assert job_id is not None

    outcomes = []
    for attempt in (1, 2, 3):
        job = task_queue.claim(queue_conn)
        assert job is not None
        assert job.attempts == attempt
        outcomes.append(task_queue.fail(queue_conn, job, f"boom {attempt}"))

    assert outcomes == ["requeued", "requeued", "failed"]
    assert row(queue_conn, job_id) == ("failed", 3, "boom 3")
    assert task_queue.claim(queue_conn) is None


def test_a_job_left_running_past_the_timeout_is_claimed_again(queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop")
    assert job_id is not None
    first = task_queue.claim(queue_conn)
    assert first is not None

    assert task_queue.requeue_stale(queue_conn, 60) == 0
    assert task_queue.claim(queue_conn) is None

    age_lock(queue_conn, job_id, 120)
    assert task_queue.requeue_stale(queue_conn, 60) == 1
    second = task_queue.claim(queue_conn)
    assert second is not None
    assert (second.id, second.attempts) == (job_id, 2)


def test_a_stale_job_with_no_attempts_left_fails_instead_of_looping(queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop", max_attempts=1)
    assert job_id is not None
    assert task_queue.claim(queue_conn) is not None
    age_lock(queue_conn, job_id, 120)

    assert task_queue.requeue_stale(queue_conn, 60) == 1
    status, attempts, error = row(queue_conn, job_id)
    assert (status, attempts) == ("failed", 1)
    assert "visibility timeout" in error


def test_a_slow_worker_cannot_complete_a_job_that_was_handed_on(queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop")
    assert job_id is not None
    slow = task_queue.claim(queue_conn)
    assert slow is not None
    age_lock(queue_conn, job_id, 120)
    task_queue.requeue_stale(queue_conn, 60)
    fast = task_queue.claim(queue_conn)
    assert fast is not None

    assert task_queue.complete(queue_conn, slow) is False
    assert task_queue.fail(queue_conn, slow, "late") == "lost"
    assert task_queue.complete(queue_conn, fast) is True
    assert row(queue_conn, job_id)[0] == "done"
