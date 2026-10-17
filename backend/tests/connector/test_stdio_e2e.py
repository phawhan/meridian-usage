"""End to end, as a host runs it: the service as a real uvicorn process, the connector as a
subprocess speaking MCP over stdio. The three cases from the brief, in prod as Priya."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import load_policy
from app.provisioning.manifest import build_manifest, dump_manifest
from tests.connector.harness import PRIYA, payload

pytestmark = pytest.mark.anyio
BACKEND = REPO_ROOT / "backend"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    root = tmp_path_factory.mktemp("e2e")
    shutil.copytree(REPO_ROOT / "data", root / "data")
    url = f"http://127.0.0.1:{free_port()}"
    env = os.environ | {
        "APP_ENV": "prod",
        "DB_PATH": str(root / "prod.db"),
        "DATA_DIR": str(root / "data"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", url.rsplit(":", 1)[1]],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                if httpx2.get(f"{url}/api/v1/healthz").status_code == 200:
                    break
            except httpx2.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("usage service did not start")
        groups = [
            g["group_id"]
            for g in json.loads((REPO_ROOT / "data/directory/groups.json").read_text())["groups"]
        ]
        manifest = root / "permissions.json"
        policy = load_policy(Settings(app_env="prod"))
        manifest.write_text(dump_manifest(build_manifest(policy, groups)))
        yield url, manifest
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def test_three_demo_cases_over_stdio(service: tuple[str, Path]) -> None:
    url, manifest = service
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.connector.main", "--user", PRIYA, "--env", "prod"]
        + ["--manifest", str(manifest), "--api-url", url],
        cwd=BACKEND,
    )
    async with Client(params) as client:
        allowed = await client.call_tool("usage_summary", {"period": "last_30_days"})
        cross = await client.call_tool("usage_summary", {"group": "finance", "period": "2026-09"})
        write = await client.call_tool(
            "set_capability", {"group": "finance", "capability": "web-search", "enabled": False}
        )
    assert not allowed.is_error and payload(allowed)["group"] == "clinical-operations"
    assert cross.is_error and payload(cross)["error"] == "permission_denied"
    assert write.is_error and payload(write)["required_scope"] == "capabilities:write"
