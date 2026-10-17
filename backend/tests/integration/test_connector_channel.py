"""X-Channel: connector. The usage-connector switch gates the assistant, not the admin console
(D1, D37). Prod baseline: switch on for it-platform and clinical-operations only."""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Settings
from app.main import create_app
from tests.contract import assert_denial

PRIYA = "user_E7691888F28227066DD2FB86"  # team lead, clinical-operations (switch on)
SOFIA = "user_0CF0516C4D9067BED584DB3F"  # team lead, finance (switch off in prod)
CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin, it-platform (switch on)


@pytest.fixture
def prod(tmp_path: Any) -> Iterator[TestClient]:
    shutil.copytree(REPO_ROOT / "data", tmp_path / "data")
    settings = Settings(app_env="prod", db_path=tmp_path / "prod.db", data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as client:
        yield client


def call(
    client: TestClient,
    user: str,
    path: str,
    method: str = "GET",
    channel: str | None = "connector",
    **kw: Any,
) -> tuple[int, Any]:
    headers = {"X-User-Id": user} | ({"X-Channel": channel} if channel else {})
    response = client.request(method, f"/api/v1{path}", headers=headers, **kw)
    return response.status_code, response.json()


def last_denial(client: TestClient) -> tuple[Any, ...]:
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    with closing(sqlite3.connect(settings.database_file)) as conn:
        row: tuple[Any, ...] = conn.execute(
            "SELECT channel, caller, action, target_group FROM access_denial ORDER BY id DESC"
        ).fetchone()
    return row


def test_switch_off_refuses_every_connector_route(prod: TestClient) -> None:
    for path in (
        "/usage/summary?period=2026-09",
        "/usage/top-users?period=2026-09",
        "/capabilities",
    ):
        status, body = call(prod, SOFIA, path)
        assert status == 403, path
        assert_denial(body)
        assert "switched off for your group (finance) in prod" in body["reason"]
    assert last_denial(prod) == ("connector", SOFIA, "use_connector", "finance")


def test_admin_console_is_not_gated(prod: TestClient) -> None:
    assert call(prod, SOFIA, "/usage/summary?period=2026-09", channel=None)[0] == 200
    assert call(prod, SOFIA, "/usage/summary?period=2026-09", channel="api")[0] == 200


def test_switch_on_allows(prod: TestClient) -> None:
    status, body = call(prod, PRIYA, "/usage/summary?period=2026-09")
    assert status == 200 and body["group"] == "clinical-operations"


def test_switch_gates_the_caller_not_the_data(prod: TestClient) -> None:
    status, body = call(prod, CHLOE, "/usage/summary?period=2026-09&group=finance")
    assert status == 200 and body["group"] == "finance"


def test_cross_group_refusal_is_logged_as_connector(prod: TestClient) -> None:
    status, body = call(prod, PRIYA, "/usage/summary?period=2026-09&group=finance")
    assert status == 403
    assert_denial(body)
    assert last_denial(prod) == ("connector", PRIYA, "read_usage", "finance")


def test_switching_it_off_takes_effect_on_the_next_request(prod: TestClient) -> None:
    path = "/capabilities/clinical-operations/usage-connector"
    assert call(prod, CHLOE, path, "PUT", channel=None, json={"enabled": False})[0] == 200
    assert call(prod, PRIYA, "/usage/summary?period=2026-09")[0] == 403


def test_identity_lookup_is_not_gated(prod: TestClient) -> None:
    assert call(prod, SOFIA, "/me")[0] == 200


def test_unknown_channel_is_rejected(prod: TestClient) -> None:
    assert call(prod, PRIYA, "/usage/summary?period=2026-09", channel="assistant")[0] == 422


def test_unidentified_connector_request_is_logged_as_connector(prod: TestClient) -> None:
    assert call(prod, "user_NOPE", "/capabilities")[0] == 401
    assert last_denial(prod)[:3] == ("connector", "user_NOPE", "identify")
