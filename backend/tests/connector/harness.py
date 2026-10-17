"""Run the connector against the real FastAPI app, in process, over the MCP protocol.

The connector's HTTP requests go through RecordingTransport into the ASGI app, so a test can
assert that a refused call sent nothing to the service (no data can have come back)."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any

import httpx2
from fastapi.testclient import TestClient
from mcp.client import Client

from app.connector.config import ConnectorConfig
from app.connector.main import connect, make_server
from app.core.config import Environment
from app.core.env_config import Policy
from app.db.session import connect as db_connect
from app.provisioning.manifest import build_manifest, dump_manifest
from app.repositories import directory

DANIEL = "user_699C48763F6FA2958D2CDB5D"  # member, clinical-operations
PRIYA = "user_E7691888F28227066DD2FB86"  # team lead, clinical-operations
SOFIA = "user_0CF0516C4D9067BED584DB3F"  # team lead, finance (usage-connector off in prod)
CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin, it-platform


STARTUP_PATHS = ("/healthz", "/periods", "/me")  # read once when the connector starts


class RecordingTransport(httpx2.AsyncBaseTransport):
    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        self.inner = inner
        self.requests: list[str] = []  # "METHOD /path"

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(f"{request.method} {request.url.path.removeprefix('/api/v1')}")
        return await self.inner.handle_async_request(request)

    def data_requests(self) -> list[str]:
        return [r for r in self.requests if r.split()[1] not in STARTUP_PATHS]


def write_manifest(app: TestClient, folder: Path) -> Path:
    policy: Policy = app.app.state.policy  # type: ignore[attr-defined]
    with closing(db_connect(app.app.state.settings.database_file)) as conn:  # type: ignore[attr-defined]
        groups = [g.group_id for g in directory.list_groups(conn) if g.active]
    path = folder / f"{policy.environment}.permissions.json"
    path.write_text(dump_manifest(build_manifest(policy, groups)))
    return path


@asynccontextmanager
async def mcp_session(
    app: TestClient, env: Environment, user: str, manifest: Path
) -> AsyncIterator[tuple[Client, RecordingTransport]]:
    transport = RecordingTransport(httpx2.ASGITransport(app=app.app))
    config = ConnectorConfig(user, env, manifest, api_url="http://usage-service")
    connector, loaded = await connect(config, transport)
    try:
        async with Client(make_server(connector, loaded)) as client:
            yield client, transport
    finally:
        await connector.service.aclose()


def payload(result: Any) -> Any:
    """The JSON the model reads (text content), parsed."""
    return json.loads(result.content[0].text)
