import logging
import signal
import sys
import threading
from types import FrameType

from psycopg_pool import ConnectionPool

from ats.db import task_queue
from ats.db.task_queue import Job
from ats.worker.registry import HANDLERS

log = logging.getLogger(__name__)


def install_signal_handlers(stop: threading.Event) -> None:
    """Ask the loop to stop. The job in progress finishes first, then the worker exits."""

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        log.info("received signal %s, finishing the current job and stopping", signum)
        stop.set()

    signals = [signal.SIGINT, signal.SIGTERM]
    # Windows: Ctrl+Break is the only catchable console signal. The platform check (not hasattr)
    # lets pyright drop this branch when type-checking for Linux, where SIGBREAK does not exist.
    if sys.platform == "win32":
        signals.append(signal.SIGBREAK)
    for sig in signals:
        signal.signal(sig, request_stop)


def run_job(pool: ConnectionPool, job: Job) -> None:
    handler = HANDLERS.get(job.job_type)
    try:
        if handler is None:
            raise LookupError(f"no handler registered for job type {job.job_type!r}")
        handler(job, pool)
    except Exception as exc:
        log.exception("job %s (%s) failed on attempt %s", job.id, job.job_type, job.attempts)
        with pool.connection() as conn:
            outcome = task_queue.fail(conn, job, f"{type(exc).__name__}: {exc}")
        log.info("job %s %s", job.id, outcome)
        return
    with pool.connection() as conn:
        if not task_queue.complete(conn, job):
            log.warning("job %s finished after it was handed to another worker", job.id)


def run(
    pool: ConnectionPool,
    stop: threading.Event,
    *,
    poll_interval_s: float,
    visibility_timeout_s: float,
) -> None:
    while not stop.is_set():
        try:
            with pool.connection() as conn:
                released = task_queue.requeue_stale(conn, visibility_timeout_s)
                job = task_queue.claim(conn)
            if released:
                log.warning("released %s stale job(s)", released)
        except Exception:
            # A database outage must not kill the worker; the pool reconnects on its own.
            log.exception("queue poll failed")
            stop.wait(poll_interval_s)
            continue
        if job is None:
            stop.wait(poll_interval_s)
            continue
        log.info("running job %s (%s), attempt %s", job.id, job.job_type, job.attempts)
        run_job(pool, job)
