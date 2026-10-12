"""Capability endpoints. Directory data only (no usage needed), fresh database per test."""

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Settings
from app.main import create_app
from tests.contract import assert_denial, assert_tool_output

PRIYA = "user_E7691888F28227066DD2FB86"  # team lead, clinical-operations
CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin, it-platform

Start = Callable[[str], TestClient]


@pytest.fixture
def start(tmp_path: Path) -> Iterator[Start]:
    shutil.copytree(REPO_ROOT / "data" / "directory", tmp_path / "data" / "directory")
    running: list[TestClient] = []

    def start_app(env: str) -> TestClient:
        settings = Settings(app_env=env, db_path=tmp_path / f"{env}.db", data_dir=tmp_path / "data")  # type: ignore[arg-type]
        client = TestClient(create_app(settings)).__enter__()
        running.append(client)
        return client

    yield start_app
    for client in running:
        client.__exit__(None, None, None)


def call(client: TestClient, method: str, path: str, user: str, **kwargs: Any) -> tuple[int, Any]:
    response = client.request(method, f"/api/v1{path}", headers={"X-User-Id": user}, **kwargs)
    return response.status_code, response.json()


def test_team_lead_reads_only_their_groups_switches(start: Start) -> None:
    status, body = call(start("prod"), "GET", "/capabilities", PRIYA)

    assert status == 200
    assert_tool_output("capability_status", body)
    assert {(s["group"], s["capability"], s["enabled"]) for s in body} == {
        ("clinical-operations", "usage-connector", True),
        ("clinical-operations", "web-search", True),
        ("clinical-operations", "code-execution", False),
    }


def test_team_lead_cannot_change_switches_in_prod(start: Start) -> None:
    status, body = call(
        start("prod"),
        "PUT",
        "/capabilities/clinical-operations/code-execution",
        PRIYA,
        json={"enabled": True},
    )
    assert status == 403
    assert_denial(body)
    assert body["required_scope"] == "capabilities:write"


def test_team_lead_changes_own_group_in_staging_but_not_others(start: Start) -> None:
    client = start("staging")
    status, body = call(
        client,
        "PUT",
        "/capabilities/clinical-operations/code-execution",
        PRIYA,
        json={"enabled": True},
    )
    assert status == 200
    assert (body["enabled"], body["drift"], body["updated_by"]) == (True, True, PRIYA)

    status, body = call(
        client, "PUT", "/capabilities/finance/code-execution", PRIYA, json={"enabled": True}
    )
    assert status == 403 and "may only change their own group" in body["reason"]


def test_admin_change_persists_across_restart_and_is_audited(start: Start) -> None:
    status, body = call(
        start("prod"), "PUT", "/capabilities/finance/usage-connector", CHLOE, json={"enabled": True}
    )
    assert status == 200
    assert_tool_output("set_capability", body)

    restarted = start("prod")
    _, states = call(restarted, "GET", "/capabilities", CHLOE, params={"group": "finance"})
    _, audit = call(restarted, "GET", "/capabilities/audit", CHLOE, params={"group": "finance"})

    assert next(s for s in states if s["capability"] == "usage-connector")["enabled"] is True
    latest = audit[0]
    assert (latest["action"], latest["old_enabled"], latest["new_enabled"], latest["by"]) == (
        "set",
        False,
        True,
        CHLOE,
    )


def test_reset_returns_to_the_baseline(start: Start) -> None:
    client = start("prod")
    call(client, "PUT", "/capabilities/finance/usage-connector", CHLOE, json={"enabled": True})

    status, body = call(client, "POST", "/capabilities/finance/usage-connector/reset", CHLOE)

    assert status == 200 and (body["enabled"], body["baseline"], body["drift"]) == (
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("path", "payload", "expected"),
    [
        ("/capabilities/finance/telepathy", {"enabled": True}, 422),
        ("/capabilities/finance/web-search", {"enabled": "yes please"}, 422),
        ("/capabilities/legal/web-search", {"enabled": True}, 404),
    ],
)
def test_bad_writes_are_refused(start: Start, path: str, payload: object, expected: int) -> None:
    assert call(start("prod"), "PUT", path, CHLOE, json=payload)[0] == expected


def test_directory_lists_active_users_for_the_persona_switcher(start: Start) -> None:
    response = start("prod").get("/api/v1/directory/users")
    assert response.status_code == 200 and len(response.json()) == 22
