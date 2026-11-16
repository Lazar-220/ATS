from collections.abc import Iterable

from psycopg_pool import ConnectionPool


def read_schema_version(pool: ConnectionPool) -> str:
    """The Alembic revision the database is at, or why it is not known."""
    try:
        with pool.connection() as conn:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except Exception as exc:  # a missing table or a down database must not stop the worker
        return f"unknown ({type(exc).__name__})"
    return str(row[0]) if row else "none"


def startup_summary(
    *,
    version: str,
    schema_version: str,
    handlers: Iterable[str],
    llm_model: str,
    llm_rpm: int,
    llm_key_set: bool,
) -> str:
    """One line a person can compare with `git log`, `alembic heads` and the expected jobs.

    The handler list is the quickest tell for a stale worker: a job type it does not list is
    one it cannot run. The key itself is never logged.
    """
    return (
        f"worker starting: code={version} schema={schema_version} "
        f"handlers={','.join(sorted(handlers))} "
        f"llm_model={llm_model} llm_rpm={llm_rpm} llm_key={'set' if llm_key_set else 'MISSING'}"
    )
