from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from ats.api.main import app
from ats.db.pool import create_pool
from ats.llm.fake import FakeLLMClient
from ats.pipeline.requirements import RequirementDraft, RequirementList
from ats.settings import get_settings
from ats.worker import ingest, position_setup  # noqa: F401  (importing registers the handlers)
from integration.test_worker import start_loop

TEST_DB = "ats_test"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def with_dbname(url: str, dbname: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{dbname}"))


@pytest.fixture(scope="session")
def test_db_url(monkeypatch_session: pytest.MonkeyPatch) -> Iterator[str]:
    """A throwaway migrated database, so tests never touch the development data."""
    base = get_settings().database_url
    admin = with_dbname(base, "postgres")
    url = with_dbname(base, TEST_DB)

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")

    monkeypatch_session.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    yield url

    get_settings.cache_clear()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")


@pytest.fixture(scope="session")
def monkeypatch_session() -> Iterator[pytest.MonkeyPatch]:
    patch = pytest.MonkeyPatch()
    yield patch
    patch.undo()


@pytest.fixture
def conn(test_db_url: str) -> Iterator[psycopg.Connection[DictRow]]:
    """An autocommit connection to a database emptied of rows before each test."""
    with psycopg.Connection[DictRow].connect(
        test_db_url, autocommit=True, row_factory=dict_row
    ) as connection:
        connection.execute(
            "TRUNCATE task_queue, verdict, assessment, request_candidate, ranking_request, "
            "document, candidate, requirement, job_position RESTART IDENTITY CASCADE"
        )
        yield connection


@pytest.fixture
def queue_conn(test_db_url: str) -> Iterator[psycopg.Connection[Any]]:
    """Tuple-row autocommit connection (what the pool hands the queue) with an empty queue."""
    with psycopg.connect(test_db_url, autocommit=True) as connection:
        connection.execute("TRUNCATE task_queue RESTART IDENTITY")
        yield connection


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLMClient:
    """No integration test reaches the real model. Set `.responder` to script the answer."""
    one = RequirementDraft(
        id=1, text="Python", kind="mandatory", weight=1, min_months=None, parent=None
    )
    fake = FakeLLMClient(responder=lambda _request, _schema: RequirementList(requirements=[one]))
    monkeypatch.setattr(position_setup, "get_llm_client", lambda: fake)
    return fake


@pytest.fixture
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection[DictRow]
) -> Iterator[TestClient]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def worker(test_db_url: str, client: TestClient) -> Iterator[ConnectionPool]:
    """The real worker loop on a thread: results appear without calling a handler."""
    pool = create_pool(test_db_url, 4)
    pool.open(wait=True, timeout=10)
    stop, thread = start_loop(pool)
    yield pool
    stop.set()
    thread.join(timeout=10)
    pool.close()
