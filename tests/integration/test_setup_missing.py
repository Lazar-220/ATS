"""`make setup-missing`: recovery for positions whose setup job was never enqueued."""

from collections.abc import Iterator
from typing import Any, LiteralString
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.llm.fake import FakeLLMClient
from ats.services.requirements import POSITION_SETUP_JOB, find_stranded_positions
from ats.worker import setup_missing
from integration.test_worker import wait_for

pytestmark = pytest.mark.integration

type Conn = psycopg.Connection[DictRow]
type Db = psycopg.Connection[Any]


@pytest.fixture
def db(test_db_url: str, conn: Conn) -> Iterator[Db]:
    """Tuple-row connection, which is what the pool hands the code under test. `conn` (dict
    rows, tables emptied) stays for seeding and assertions."""
    with psycopg.connect(test_db_url, autocommit=True) as connection:
        yield connection


def add_position(conn: Conn, sha: str, *, text: str | None = "Requires Java") -> UUID:
    row = conn.execute(
        "INSERT INTO job_position (source_sha256, posting_text) VALUES (%s, %s) RETURNING id",
        (sha, text),
    ).fetchone()
    assert row is not None
    conn.execute(
        "INSERT INTO document (kind, sha256, filename, status) "
        "VALUES ('posting', %s, %s, 'extracted')",
        (sha, f"{sha}.pdf"),
    )
    return row["id"]


def count(conn: Conn, sql: LiteralString) -> int:
    row = conn.execute(sql).fetchone()
    assert row is not None
    return int(row["n"])


def test_only_a_position_with_text_and_no_requirements_and_no_job_is_stranded(
    conn: Conn,
    db: Db,
) -> None:
    stranded = add_position(conn, "stranded")
    add_position(conn, "no-text", text=None)
    with_requirements = add_position(conn, "has-requirements")
    conn.execute(
        "INSERT INTO requirement (position_id, rubric_version, text, kind) "
        "VALUES (%s, 1, 'Java', 'mandatory')",
        (with_requirements,),
    )
    for sha, status in (("queued", "queued"), ("failed", "failed"), ("done", "done")):
        position = add_position(conn, sha)
        conn.execute(
            "INSERT INTO task_queue (job_type, payload, dedup_key, status) "
            "VALUES (%s, '{}', %s, %s)",
            (POSITION_SETUP_JOB, f"{POSITION_SETUP_JOB}:{position}", status),
        )

    found = find_stranded_positions(db)

    # A job in any state means the position is not stranded: a failed one is retried by
    # uploading the posting again, not by this command.
    assert [(p.id, p.filename) for p in found] == [(stranded, "stranded.pdf")]


def test_without_yes_it_lists_and_enqueues_nothing(
    conn: Conn, db: Db, capsys: pytest.CaptureFixture[str]
) -> None:
    position = add_position(conn, "stranded")

    assert setup_missing.run(db, None, yes=False) == 0

    out = capsys.readouterr().out
    assert str(position) in out and "stranded.pdf" in out
    assert "Dry run, nothing enqueued" in out and "1 LLM call(s)" in out
    assert count(conn, "SELECT count(*) AS n FROM task_queue") == 0


def test_with_yes_it_enqueues_once_and_a_second_run_finds_nothing(
    conn: Conn, db: Db, capsys: pytest.CaptureFixture[str]
) -> None:
    position = add_position(conn, "stranded")

    assert setup_missing.run(db, None, yes=True) == 0
    assert setup_missing.run(db, None, yes=True) == 0

    jobs = conn.execute("SELECT payload, dedup_key FROM task_queue").fetchall()
    assert jobs == [
        {
            "payload": {"position_id": str(position)},
            "dedup_key": f"{POSITION_SETUP_JOB}:{position}",
        }
    ]
    assert "Nothing to do" in capsys.readouterr().out


def test_a_prefix_selects_one_position_and_leaves_the_others(conn: Conn, db: Db) -> None:
    first = add_position(conn, "first")
    second = add_position(conn, "second")

    setup_missing.run(db, str(first)[:8], yes=True)

    queued = conn.execute("SELECT dedup_key FROM task_queue").fetchall()
    assert queued == [{"dedup_key": f"{POSITION_SETUP_JOB}:{first}"}]
    assert [p.id for p in find_stranded_positions(db)] == [second]


def test_a_prefix_that_matches_nothing_is_an_error_and_enqueues_nothing(
    conn: Conn, db: Db, capsys: pytest.CaptureFixture[str]
) -> None:
    add_position(conn, "one")

    assert setup_missing.run(db, "zzzz", yes=True) == 2
    assert "matches no position" in capsys.readouterr().err
    assert count(conn, "SELECT count(*) AS n FROM task_queue") == 0


def test_a_prefix_that_matches_several_positions_is_an_error(
    conn: Conn, db: Db, capsys: pytest.CaptureFixture[str]
) -> None:
    add_position(conn, "one")
    add_position(conn, "two")

    assert setup_missing.run(db, "", yes=True) == 2  # every id starts with ""
    assert "matches 2 positions" in capsys.readouterr().err
    assert count(conn, "SELECT count(*) AS n FROM task_queue") == 0


def test_the_worker_then_extracts_the_requirements(
    worker: ConnectionPool, conn: Conn, db: Db, fake_llm: FakeLLMClient
) -> None:
    """The real loop picks up the enqueued job: one call per stranded position."""
    position = add_position(conn, "stranded")

    setup_missing.run(db, None, yes=True)
    wait_for(
        lambda: count(conn, "SELECT count(*) AS n FROM requirement") > 0,
    )

    assert len(fake_llm.calls) == 1
    row = conn.execute("SELECT position_id FROM requirement").fetchone()
    assert row is not None and row["position_id"] == position
