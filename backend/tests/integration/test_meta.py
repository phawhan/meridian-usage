from fastapi.testclient import TestClient


def test_healthz_reports_environment(client: TestClient) -> None:
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "dev"}
