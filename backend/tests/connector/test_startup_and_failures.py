"""The connector refuses to start unless manifest, service and user agree, and a failing or
misbehaving service yields an error result, never data the contract doesn't promise."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.connector.config import ConnectorConfig
from app.connector.main import StartupError, connect
from app.connector.service import ServiceError, UsageService
from app.connector.tools import UsageConnector
from app.models.domain import User
from tests.connector.harness import PRIYA, mcp_session, write_manifest

pytestmark = pytest.mark.anyio


def asgi(client: TestClient) -> httpx2.ASGITransport:
    return httpx2.ASGITransport(app=client.app)


async def start(client: TestClient, manifest: Path | None, user: str = PRIYA) -> None:
    config = ConnectorConfig(user, "dev", manifest, api_url="http://usage-service")
    connector, _ = await connect(config, asgi(client))
    await connector.service.aclose()


async def test_starts_with_a_matching_manifest(client: TestClient, tmp_path: Path) -> None:
    async with mcp_session(client, "dev", PRIYA, write_manifest(client, tmp_path)) as (c, sent):
        assert len((await c.list_tools()).tools) == 4
    assert sent.requests == ["GET /healthz", "GET /periods", "GET /me"]


async def test_refuses_a_missing_manifest(client: TestClient, tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="no permissions manifest"):
        await start(client, tmp_path / "absent.json")


async def test_refuses_a_manifest_for_another_environment(
    client: TestClient, tmp_path: Path
) -> None:
    path = write_manifest(client, tmp_path)
    path.write_text(path.read_text().replace('"environment": "dev"', '"environment": "prod"'))
    with pytest.raises(StartupError, match="is for prod, started as dev"):
        await start(client, path)


async def test_refuses_when_the_service_runs_a_different_policy(
    client: TestClient, tmp_path: Path
) -> None:
    path = write_manifest(client, tmp_path)
    manifest = json.loads(path.read_text())
    manifest["source"]["sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(StartupError, match="different environments/dev.yaml"):
        await start(client, path)


async def test_refuses_an_unknown_user(client: TestClient, tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="cannot start as user_NOPE"):
        await start(client, write_manifest(client, tmp_path), user="user_NOPE")


async def test_refuses_when_the_service_is_unreachable(client: TestClient, tmp_path: Path) -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    config = ConnectorConfig(PRIYA, "dev", write_manifest(client, tmp_path), None)
    with pytest.raises(ServiceError, match="unreachable"):
        await connect(config, httpx2.MockTransport(down))


PRIYA_USER = User(
    user_id=PRIYA,
    email="p@x",
    name="Priya",
    role="team_lead",
    group_ids=["clinical-operations"],
    active=True,
)


async def call_against(client: TestClient, respond: Any) -> Any:
    service = UsageService("http://usage-service", PRIYA, transport=httpx2.MockTransport(respond))
    connector = UsageConnector(PRIYA_USER, client.app.state.policy, service)  # type: ignore[attr-defined]
    try:
        return await connector.call("usage_summary", {"period": "2026-09"})
    finally:
        await service.aclose()


async def test_service_failure_mid_session_is_an_error_not_data(client: TestClient) -> None:
    outcome = await call_against(client, lambda request: httpx2.Response(500, text="boom"))
    assert outcome.kind == "error" and outcome.payload["error"] == "service_unavailable"


async def test_output_outside_the_contract_is_withheld(client: TestClient) -> None:
    outcome = await call_against(
        client, lambda request: httpx2.Response(200, json={"group": "finance", "rows": [1, 2]})
    )
    assert outcome.kind == "error" and outcome.payload["error"] == "contract_violation"
    assert "finance" not in json.dumps(outcome.payload)
