import pytest
from fastapi.testclient import TestClient

from ats.api.main import app

pytestmark = pytest.mark.integration


@pytest.mark.usefixtures("test_db_url")
def test_health_reports_reachable_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
