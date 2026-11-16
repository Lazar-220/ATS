from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ats.api.main import app
from ats.settings import get_settings


@pytest.fixture
def unreachable_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Port 1 is never a Postgres, so this runs without Docker.
    monkeypatch.setenv("DATABASE_URL", "postgresql://ats:ats@127.0.0.1:1/ats")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("unreachable_db")
def test_health_reports_unreachable_database_with_503() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}
