from collections.abc import Callable

from psycopg_pool import ConnectionPool

from ats.db.task_queue import Job

# The pool is passed in so a handler can open its own short transactions.
Handler = Callable[[Job, ConnectionPool], None]

HANDLERS: dict[str, Handler] = {}


def register(job_type: str) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        if job_type in HANDLERS:
            raise ValueError(f"handler already registered for {job_type!r}")
        HANDLERS[job_type] = handler
        return handler

    return decorator
