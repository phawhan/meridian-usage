"""The permission model through the MCP protocol, against the real service and starter data.

The three cases the brief names: an allowed read, a denied cross-group read and a denied
write, plus the switch, members, admins, and arguments shaped like an attempt to talk around
the rules. A denial must arrive as the contract's Denial, as an error result, and when the
connector refuses on its own, no data request may reach the service.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Environment, Settings
from app.core.contract import input_schema
from app.main import create_app
from tests.connector.harness import (
    CHLOE,
    DANIEL,
    PRIYA,
    SOFIA,
    mcp_session,
    payload,
    write_manifest,
)
from tests.contract import assert_denial, assert_tool_output

pytestmark = pytest.mark.anyio

Apps = dict[Environment, tuple[TestClient, Path]]


def _start(root: Path, env: Environment) -> tuple[TestClient, Path]:
    settings = Settings(app_env=env, db_path=root / f"{env}.db", data_dir=root / "data")
    client = TestClient(create_app(settings)).__enter__()
    return client, write_manifest(client, root)


@pytest.fixture(scope="module")
def apps(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Apps]:
    """Read-only tests share one service per environment."""
    root = tmp_path_factory.mktemp("connector")
    shutil.copytree(REPO_ROOT / "data", root / "data")
    started: Apps = {env: _start(root, env) for env in ("dev", "staging", "prod")}
    yield started
    for client, _ in started.values():
        client.__exit__(None, None, None)


@pytest.fixture
def fresh_prod(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """Tests that change a switch get their own service."""
    shutil.copytree(REPO_ROOT / "data", tmp_path / "data")
    client, manifest = _start(tmp_path, "prod")
    yield client, manifest
    client.__exit__(None, None, None)


async def test_lists_the_four_contract_tools(apps: Apps) -> None:
    async with mcp_session(*apps["prod"][:1], "prod", PRIYA, apps["prod"][1]) as (client, _):
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert sorted(tools) == ["capability_status", "set_capability", "top_users", "usage_summary"]
    for name, tool in tools.items():
        assert tool.input_schema == input_schema(name)  # type: ignore[arg-type]
    assert tools["usage_summary"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert tools["set_capability"].annotations.read_only_hint is False  # type: ignore[union-attr]


# --- the three demo cases (prod, Priya: team lead, clinical-operations) ---


async def test_allowed_read_own_group(apps: Apps) -> None:
    client_app, manifest = apps["prod"]
    async with mcp_session(client_app, "prod", PRIYA, manifest) as (client, _):
        result = await client.call_tool("usage_summary", {"period": "2026-09"})
    assert not result.is_error
    body = payload(result)
    assert_tool_output("usage_summary", body)
    assert body["group"] == "clinical-operations"
    assert body["totals"]["total_tokens"] > 0
    assert result.structured_content == body


async def test_denied_cross_group_read_sends_nothing(apps: Apps) -> None:
    client_app, manifest = apps["prod"]
    async with mcp_session(client_app, "prod", PRIYA, manifest) as (client, sent):
        result = await client.call_tool("usage_summary", {"group": "finance", "period": "2026-09"})
    assert result.is_error
    assert_denial(payload(result))
    assert payload(result) == {
        "error": "permission_denied",
        "reason": "Priya Nair may only see their own group (clinical-operations), not 'finance'",
    }
    assert sent.data_requests() == []


async def test_denied_write_sends_nothing(apps: Apps) -> None:
    client_app, manifest = apps["prod"]
    args = {"group": "clinical-operations", "capability": "web-search", "enabled": False}
    async with mcp_session(client_app, "prod", PRIYA, manifest) as (client, sent):
        result = await client.call_tool("set_capability", args)
    assert result.is_error
    assert payload(result) == {
        "error": "permission_denied",
        "reason": "role 'team_lead' does not have capabilities:write in prod",
        "required_scope": "capabilities:write",
    }
    assert sent.data_requests() == []


# --- roles and environments ---


async def test_member_has_no_usage_read_in_prod(apps: Apps) -> None:
    async with mcp_session(apps["prod"][0], "prod", DANIEL, apps["prod"][1]) as (client, sent):
        result = await client.call_tool("top_users", {"period": "2026-09"})
    assert payload(result)["required_scope"] == "usage:read"
    assert sent.data_requests() == []


async def test_member_reads_any_group_in_dev(apps: Apps) -> None:
    async with mcp_session(apps["dev"][0], "dev", DANIEL, apps["dev"][1]) as (client, _):
        result = await client.call_tool("usage_summary", {"group": "finance", "period": "2026-W36"})
    assert not result.is_error and payload(result)["group"] == "finance"


async def test_admin_reads_every_group(apps: Apps) -> None:
    async with mcp_session(apps["prod"][0], "prod", CHLOE, apps["prod"][1]) as (client, _):
        finance = await client.call_tool("usage_summary", {"group": "finance", "period": "2026-09"})
        top = await client.call_tool("top_users", {"period": "2026-09", "limit": 25})
    assert payload(finance)["group"] == "finance"
    assert_tool_output("top_users", payload(top))
    assert len({u["group"] for u in payload(top)}) > 1
    assert top.structured_content == {"result": payload(top)}


async def test_lead_sees_only_own_group_capabilities(apps: Apps) -> None:
    async with mcp_session(apps["prod"][0], "prod", PRIYA, apps["prod"][1]) as (client, _):
        result = await client.call_tool("capability_status", {})
    assert_tool_output("capability_status", payload(result))
    assert {row["group"] for row in payload(result)} == {"clinical-operations"}


async def test_lead_writes_own_group_where_allowed(apps: Apps) -> None:
    args = {"group": "clinical-operations", "capability": "code-execution", "enabled": True}
    async with mcp_session(apps["staging"][0], "staging", PRIYA, apps["staging"][1]) as (c, _):
        own = await c.call_tool("set_capability", args)
        other = await c.call_tool("set_capability", args | {"group": "finance"})
    assert_tool_output("set_capability", payload(own))
    assert payload(own)["updated_by"] == PRIYA
    assert "may only change their own group" in payload(other)["reason"]


# --- the usage-connector switch (checked by the service, live) ---


async def test_switch_off_refuses_the_group_itself(apps: Apps) -> None:
    async with mcp_session(apps["prod"][0], "prod", SOFIA, apps["prod"][1]) as (client, sent):
        result = await client.call_tool("usage_summary", {"period": "2026-09"})
    assert result.is_error
    assert_denial(payload(result))
    assert "usage connector is switched off for your group (finance)" in payload(result)["reason"]
    assert sent.data_requests() == ["GET /usage/summary"]  # refused by the second door


async def test_admin_switching_it_on_takes_effect_immediately(
    fresh_prod: tuple[TestClient, Path],
) -> None:
    app, manifest = fresh_prod
    args = {"group": "finance", "capability": "usage-connector", "enabled": True}
    async with mcp_session(app, "prod", CHLOE, manifest) as (admin, _):
        changed = await admin.call_tool("set_capability", args)
    assert payload(changed)["enabled"] is True and payload(changed)["updated_by"] == CHLOE
    async with mcp_session(app, "prod", SOFIA, manifest) as (lead, _):
        result = await lead.call_tool("usage_summary", {"period": "2026-09"})
    assert not result.is_error and payload(result)["group"] == "finance"


# --- arguments shaped like an attempt to talk around the rules ---


@pytest.mark.parametrize(
    "arguments",
    [
        {"period": "2026-09", "group": "finance", "user": CHLOE},
        {"period": "2026-09", "group": "finance", "as_role": "platform_admin"},
        {"period": "2026-09", "group": "finance; it-platform"},
        {"period": "2026-09", "group": "*"},
        {"period": "2026-09", "group": "../finance"},
        {"period": "2026-09' OR '1'='1"},
        {"group": "finance"},
    ],
)
async def test_arguments_outside_the_contract_are_rejected_unsent(
    apps: Apps, arguments: dict[str, str]
) -> None:
    async with mcp_session(apps["prod"][0], "prod", PRIYA, apps["prod"][1]) as (client, sent):
        result = await client.call_tool("usage_summary", arguments)
    assert result.is_error
    assert payload(result)["error"] == "invalid_arguments"
    assert sent.data_requests() == []


async def test_instructions_anchor_relative_dates_to_the_data(apps: Apps) -> None:
    async with mcp_session(apps["prod"][0], "prod", PRIYA, apps["prod"][1]) as (client, _):
        text = client.instructions
    assert text is not None
    assert "up to (not including) 2026-09-28" in text
    assert 'When the user says "last month", use 2026-09.' in text
    assert "no argument can change who they are" in text
