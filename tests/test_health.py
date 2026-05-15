from fastapi.testclient import TestClient

from app.main import app


def test_health_ok(monkeypatch):
    async def _mock_ok():
        return True, "ok"

    monkeypatch.setattr("app.api.routes_health.check_database", _mock_ok)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_health_database_error(monkeypatch):
    async def _mock_error():
        return False, "OperationalError"

    monkeypatch.setattr("app.api.routes_health.check_database", _mock_error)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "error:OperationalError"
