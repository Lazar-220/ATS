"""POST /hr/answers and the position reads, against a seeded position (no worker needed)."""

from typing import Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import DictRow

from ats.pipeline.requirements import RequirementList
from ats.services.requirements import insert_requirements

pytestmark = pytest.mark.integration

type Conn = psycopg.Connection[DictRow]


def req(id: int, text: str, parent: int | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "id": id,
        "text": text,
        "kind": "mandatory",
        "weight": 1,
        "min_months": None,
        "parent": parent,
    } | extra


def seed_position(conn: Conn, assessments: int = 0) -> UUID:
    row = conn.execute(
        "INSERT INTO job_position (source_sha256, posting_text) VALUES (%s, 'text') RETURNING id",
        (uuid4().hex,),
    ).fetchone()
    assert row is not None
    position_id: UUID = row["id"]
    insert_requirements(
        conn,
        position_id,
        1,
        RequirementList.model_validate(
            {"requirements": [req(1, "Java"), req(2, "3 years of Java", 1, min_months=36)]}
        ),
    )
    for _ in range(assessments):
        candidate = conn.execute("INSERT INTO candidate (full_name) VALUES ('x') RETURNING id")
        candidate_row = candidate.fetchone()
        assert candidate_row is not None
        conn.execute(
            "INSERT INTO assessment (position_id, candidate_id, rubric_version) VALUES (%s, %s, 1)",
            (position_id, candidate_row["id"]),
        )
    return position_id


def confirm(position_id: UUID, key: str, version: int = 1) -> dict[str, Any]:
    return {
        "type": "confirm",
        "position_id": str(position_id),
        "dedup_key": key,
        "rubric_version": version,
    }


def edit(position_id: UUID, key: str, requirements: list[dict[str, Any]], version: int = 1) -> Any:
    return {
        "type": "edit",
        "position_id": str(position_id),
        "dedup_key": key,
        "rubric_version": version,
        "requirements": {"requirements": requirements},
    }


def rows(conn: Conn, sql: LiteralString, *params: object) -> list[dict[str, Any]]:
    return conn.execute(sql, params).fetchall()


def test_confirm_sets_the_status_and_a_repeat_changes_nothing(
    client: TestClient, conn: Conn
) -> None:
    position = seed_position(conn)

    first = client.post("/hr/answers", json=confirm(position, "k1"))
    again = client.post("/hr/answers", json=confirm(position, "k1"))

    assert first.status_code == 200
    assert first.json() == {
        "position_id": str(position),
        "rubric_version": 1,
        "rubric_status": "confirmed",
        "rejudge_jobs": 0,
        "duplicate": False,
    }
    assert again.json() | {"duplicate": False} == first.json()
    assert again.json()["duplicate"] is True
    assert client.get(f"/positions/{position}").json()["rubric_status"] == "confirmed"
    assert len(rows(conn, "SELECT 1 FROM hr_answer")) == 1


def test_an_edit_bumps_the_version_once_and_enqueues_one_rejudge_per_assessment(
    client: TestClient, conn: Conn
) -> None:
    position = seed_position(conn, assessments=2)
    body = edit(
        position,
        "e1",
        [req(1, "Java", weight=3), req(2, "4 years of Java", 1, min_months=48), req(3, "Docker")],
    )

    first = client.post("/hr/answers", json=body)
    repeat = client.post("/hr/answers", json=body)

    assert first.status_code == 200
    assert (first.json()["rubric_version"], first.json()["rejudge_jobs"]) == (2, 2)
    assert first.json()["rubric_status"] == "unconfirmed"  # an edit does not confirm
    assert repeat.json()["duplicate"] is True
    assert (repeat.json()["rubric_version"], repeat.json()["rejudge_jobs"]) == (2, 2)

    version = rows(conn, "SELECT rubric_version FROM job_position WHERE id = %s", position)
    assert version[0]["rubric_version"] == 2
    jobs = rows(conn, "SELECT payload, dedup_key FROM task_queue WHERE job_type = 'rejudge'")
    assert len(jobs) == 2
    assert all(job["payload"]["rubric_version"] == 2 for job in jobs)
    # The old rows are kept, so verdicts written against version 1 never dangle.
    per_version = rows(
        conn,
        "SELECT rubric_version, count(*) AS n FROM requirement WHERE position_id = %s "
        "GROUP BY rubric_version ORDER BY rubric_version",
        position,
    )
    assert per_version == [{"rubric_version": 1, "n": 2}, {"rubric_version": 2, "n": 3}]


def test_the_position_read_returns_the_current_version_with_its_parent_links(
    client: TestClient, conn: Conn
) -> None:
    position = seed_position(conn)
    client.post(
        "/hr/answers",
        json=edit(position, "e1", [req(1, "Python", weight=4)]),
    )

    detail = client.get(f"/positions/{position}").json()

    assert detail["rubric_version"] == 2
    assert [r["text"] for r in detail["requirements"]] == ["Python"]
    assert detail["requirements"][0]["weight"] == 4
    assert detail["setup_status"] == "done"


def test_a_parent_link_survives_the_edit(client: TestClient, conn: Conn) -> None:
    position = seed_position(conn)
    client.post(
        "/hr/answers",
        json=edit(position, "e1", [req(5, "Java"), req(6, "3 years", 5, min_months=36)]),
    )

    requirements = client.get(f"/positions/{position}").json()["requirements"]

    assert requirements[1]["parent_id"] == requirements[0]["id"]
    assert requirements[1]["min_months"] == 36


def test_editing_a_confirmed_rubric_leaves_it_confirmed(client: TestClient, conn: Conn) -> None:
    position = seed_position(conn)
    client.post("/hr/answers", json=confirm(position, "c1"))

    result = client.post("/hr/answers", json=edit(position, "e1", [req(1, "Java")]))

    assert (result.json()["rubric_version"], result.json()["rubric_status"]) == (2, "confirmed")


def test_an_answer_for_an_old_version_is_rejected(client: TestClient, conn: Conn) -> None:
    position = seed_position(conn)
    client.post("/hr/answers", json=edit(position, "e1", [req(1, "Java")]))

    stale = client.post("/hr/answers", json=confirm(position, "c1", version=1))

    assert stale.status_code == 409
    assert "version 2" in stale.json()["detail"]
    assert rows(conn, "SELECT rubric_status FROM job_position")[0]["rubric_status"] == (
        "unconfirmed"
    )


def test_a_dedup_key_cannot_be_reused_for_a_different_request(
    client: TestClient, conn: Conn
) -> None:
    position = seed_position(conn)
    other = seed_position(conn)
    client.post("/hr/answers", json=edit(position, "same", [req(1, "Java")]))

    different_content = client.post("/hr/answers", json=edit(position, "same", [req(1, "Go")]))
    other_position = client.post("/hr/answers", json=confirm(other, "same"))

    assert different_content.status_code == 409
    assert other_position.status_code == 409
    assert rows(conn, "SELECT rubric_version FROM job_position WHERE id = %s", position)[0] == {
        "rubric_version": 2
    }


@pytest.mark.parametrize(
    "requirements",
    [
        [req(1, "Java", 1)],  # its own parent
        [req(1, "A", 2), req(2, "B", 1)],  # a cycle
        [req(1, "A", 9)],  # unknown parent
        [],  # an empty list
        [req(1, "A", weight=9)],
    ],
)
def test_an_invalid_requirement_list_is_a_422_and_changes_nothing(
    client: TestClient, conn: Conn, requirements: list[dict[str, Any]]
) -> None:
    position = seed_position(conn)

    response = client.post("/hr/answers", json=edit(position, "e1", requirements))

    assert response.status_code == 422
    assert rows(conn, "SELECT rubric_version FROM job_position")[0]["rubric_version"] == 1
    assert rows(conn, "SELECT 1 FROM hr_answer") == []


def test_an_unknown_position_is_a_404(client: TestClient) -> None:
    assert client.post("/hr/answers", json=confirm(uuid4(), "k")).status_code == 404
    assert client.get(f"/positions/{uuid4()}").status_code == 404


def test_the_position_list_says_why_a_position_has_no_requirements(
    client: TestClient, conn: Conn
) -> None:
    seed_position(conn)
    rejected = conn.execute(
        "INSERT INTO job_position (source_sha256) VALUES ('scan') RETURNING id"
    ).fetchone()
    assert rejected is not None
    conn.execute(
        "INSERT INTO document (kind, sha256, filename, status, status_message) "
        "VALUES ('posting', 'scan', 'scan.pdf', 'rejected', 'looks like a scan')"
    )

    listed = {p["id"]: p for p in client.get("/positions").json()}

    bad = listed[str(rejected["id"])]
    assert (bad["setup_status"], bad["setup_message"]) == ("failed", "looks like a scan")
    assert bad["filename"] == "scan.pdf"
    assert sorted(p["setup_status"] for p in listed.values()) == ["done", "failed"]
