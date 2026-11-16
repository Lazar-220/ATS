"""Built-in handlers. Importing this module registers them."""

import time

from ats.db.task_queue import Job
from ats.worker.registry import register


@register("noop")
def noop(job: Job) -> None:
    """Does nothing, optionally for `sleep_s` seconds, so tests can catch a job mid-run."""
    time.sleep(float(job.payload.get("sleep_s", 0)))
