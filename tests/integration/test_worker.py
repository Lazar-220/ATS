import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from ats.db import task_queue
from ats.db.pool import create_pool
from ats.worker import handlers  # noqa: F401  (registers noop)
from ats.worker.loop import run
from ats.worker.registry import HANDLERS
from ats.worker.startup import read_schema_version

pytestmark = pytest.mark.integration

type Conn = psycopg.Connection[Any]


@pytest.fixture
def pool(test_db_url: str, queue_conn: Conn) -> Iterator[ConnectionPool]:
    pool = create_pool(test_db_url, 4)
    pool.open(wait=True, timeout=10)
    yield pool
    pool.close()


def status_of(conn: Conn, job_id: int) -> tuple[str, int, str | None]:
    found = conn.execute(
        "SELECT status, attempts, error FROM task_queue WHERE id = %s", (job_id,)
    ).fetchone()
    assert found is not None
    return found


def wait_for(condition: Callable[[], bool], timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.1)
    pytest.fail("condition not met in time")


def start_loop(pool: ConnectionPool) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    thread = threading.Thread(
        target=run,
        args=(pool, stop),
        kwargs={"poll_interval_s": 0.05, "visibility_timeout_s": 300},
    )
    thread.start()
    return stop, thread


def test_worker_completes_a_job(pool: ConnectionPool, queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop")
    assert job_id is not None
    stop, thread = start_loop(pool)
    try:
        wait_for(lambda: status_of(queue_conn, job_id)[0] == "done")
    finally:
        stop.set()
        thread.join(timeout=10)
    assert not thread.is_alive()


def test_shutdown_lets_the_running_job_finish(pool: ConnectionPool, queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop", {"sleep_s": 1})
    assert job_id is not None
    stop, thread = start_loop(pool)
    wait_for(lambda: status_of(queue_conn, job_id)[0] == "running")

    stop.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert status_of(queue_conn, job_id)[0] == "done"


def test_a_failing_handler_is_retried_then_failed_with_the_error_stored(
    pool: ConnectionPool, queue_conn: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_job: task_queue.Job, _pool: ConnectionPool) -> None:
        raise RuntimeError("kaput")

    monkeypatch.setitem(HANDLERS, "boom", boom)
    job_id = task_queue.enqueue(queue_conn, "boom")
    assert job_id is not None
    stop, thread = start_loop(pool)
    try:
        wait_for(lambda: status_of(queue_conn, job_id)[0] == "failed")
    finally:
        stop.set()
        thread.join(timeout=10)
    assert status_of(queue_conn, job_id) == ("failed", 3, "RuntimeError: kaput")


def test_a_job_without_a_handler_fails(pool: ConnectionPool, queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "does_not_exist", max_attempts=1)
    assert job_id is not None
    stop, thread = start_loop(pool)
    try:
        wait_for(lambda: status_of(queue_conn, job_id)[0] == "failed")
    finally:
        stop.set()
        thread.join(timeout=10)
    assert "no handler registered" in str(status_of(queue_conn, job_id)[2])


def spawn_worker(test_db_url: str) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "DATABASE_URL": test_db_url,
        "QUEUE_VISIBILITY_TIMEOUT_S": "2",
        "WORKER_POLL_INTERVAL_S": "0.2",
    }
    return subprocess.Popen([sys.executable, "-m", "ats.worker"], env=env)


def test_killing_the_worker_mid_job_loses_nothing(test_db_url: str, queue_conn: Conn) -> None:
    job_id = task_queue.enqueue(queue_conn, "noop", {"sleep_s": 3})
    assert job_id is not None

    first = spawn_worker(test_db_url)
    try:
        wait_for(lambda: status_of(queue_conn, job_id)[0] == "running", timeout_s=60)
        first.kill()  # no cleanup runs: the job is left in `running`
        first.wait(timeout=10)
        assert status_of(queue_conn, job_id)[0] == "running"

        second = spawn_worker(test_db_url)
        try:
            wait_for(lambda: status_of(queue_conn, job_id)[0] == "done", timeout_s=60)
        finally:
            second.kill()
            second.wait(timeout=10)
    finally:
        first.kill()

    status, attempts, _ = status_of(queue_conn, job_id)
    assert (status, attempts) == ("done", 2)


def test_the_schema_version_is_read_from_the_database(pool: ConnectionPool) -> None:
    assert read_schema_version(pool) == "0003"
