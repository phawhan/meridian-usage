import hashlib

from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT


def test_healthz_reports_environment_and_policy_version(client: TestClient) -> None:
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    expected = hashlib.sha256((REPO_ROOT / "environments" / "dev.yaml").read_bytes()).hexdigest()
    assert response.json() == {"status": "ok", "environment": "dev", "policy_sha256": expected}
