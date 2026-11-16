from typing import LiteralString

import psycopg
import pytest
from psycopg.rows import DictRow

pytestmark = pytest.mark.integration

V1_TABLES = {
    "job_position",
    "requirement",
    "candidate",
    "document",
    "ranking_request",
    "request_candidate",
    "assessment",
    "verdict",
    "task_queue",
}

type Conn = psycopg.Connection[DictRow]


def scalar(conn: Conn, sql: LiteralString, params: tuple[object, ...] = ()) -> object:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def seed_graph(conn: Conn) -> tuple[object, object]:
    """One position with a requirement, an assessment and a verdict. Returns (position, req)."""
    position = scalar(conn, "INSERT INTO job_position (source_sha256) VALUES ('p') RETURNING id")
    requirement = conn.execute(
        "INSERT INTO requirement (position_id, rubric_version, text, kind) "
        "VALUES (%s, 1, 'Python', 'mandatory') RETURNING id",
        (position,),
    ).fetchone()
    assert requirement is not None
    candidate = scalar(conn, "INSERT INTO candidate (full_name) VALUES ('x') RETURNING id")
    assessment = scalar(
        conn,
        "INSERT INTO assessment (position_id, candidate_id, rubric_version) "
        "VALUES (%s, %s, 1) RETURNING id",
        (position, candidate),
    )
    conn.execute(
        "INSERT INTO verdict (assessment_id, requirement_id, verdict) VALUES (%s, %s, 'not_met')",
        (assessment, requirement["id"]),
    )
    return position, requirement["id"]


def test_baseline_creates_the_nine_v1_tables(conn: Conn) -> None:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    ).fetchall()
    assert {row["table_name"] for row in rows} == V1_TABLES


def test_required_day_one_columns_exist(conn: Conn) -> None:
    rows = conn.execute(
        "SELECT table_name || '.' || column_name AS name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ).fetchall()
    names = {row["name"] for row in rows}
    assert {
        "document.raw_text",
        "job_position.source_sha256",
        "job_position.rubric_version",
        "job_position.rubric_status",
    } <= names


def test_deleting_a_position_removes_its_whole_graph(conn: Conn) -> None:
    position, _ = seed_graph(conn)
    conn.execute("DELETE FROM job_position WHERE id = %s", (position,))
    assert scalar(conn, "SELECT count(*) FROM requirement") == 0
    assert scalar(conn, "SELECT count(*) FROM assessment") == 0
    assert scalar(conn, "SELECT count(*) FROM verdict") == 0


def test_a_requirement_with_verdicts_cannot_be_deleted(conn: Conn) -> None:
    _, requirement = seed_graph(conn)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("DELETE FROM requirement WHERE id = %s", (requirement,))


def test_assessment_status_is_unconstrained(conn: Conn) -> None:
    position, _ = seed_graph(conn)
    other = scalar(conn, "INSERT INTO candidate (full_name) VALUES ('y') RETURNING id")
    conn.execute(
        "INSERT INTO assessment (position_id, candidate_id, rubric_version, status) "
        "VALUES (%s, %s, 1, 'waiting_hr')",
        (position, other),
    )


def test_requirement_kind_is_required(conn: Conn) -> None:
    position = scalar(conn, "INSERT INTO job_position (source_sha256) VALUES ('q') RETURNING id")
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute(
            "INSERT INTO requirement (position_id, rubric_version, text) VALUES (%s, 1, 't')",
            (position,),
        )


def test_quote_offsets_are_documented_against_raw_text(conn: Conn) -> None:
    rows = conn.execute(
        "SELECT a.attname AS col, d.description FROM pg_description d "
        "JOIN pg_attribute a ON a.attrelid = d.objoid AND a.attnum = d.objsubid "
        "WHERE d.objoid = 'verdict'::regclass"
    ).fetchall()
    assert {row["col"] for row in rows} == {"char_start", "char_end"}
    assert all("raw_text" in str(row["description"]) for row in rows)
