"""Usage endpoints on the full starter data, per environment. Read-only, so one app per
environment per module."""

import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Settings
from app.main import create_app
from tests.contract import assert_denial, assert_tool_output

DANIEL = "user_699C48763F6FA2958D2CDB5D"  # member, clinical-operations
PRIYA = "user_E7691888F28227066DD2FB86"  # team lead, clinical-operations
CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin, it-platform

Get = Callable[..., Any]


@pytest.fixture(scope="module")
def clients(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, TestClient]]:
    root = tmp_path_factory.mktemp("usage_api")
    shutil.copytree(REPO_ROOT / "data", root / "data")
    clients = {}
    for env in ("dev", "staging", "prod"):
        settings = Settings(app_env=env, db_path=root / f"{env}.db", data_dir=root / "data")
        clients[env] = TestClient(create_app(settings)).__enter__()
    yield clients
    for client in clients.values():
        client.__exit__(None, None, None)


def get(clients: dict[str, TestClient], env: str, user: str, path: str, **params: Any) -> Any:
    response = clients[env].get(f"/api/v1{path}", params=params, headers={"X-User-Id": user})
    return response.status_code, response.json()


def golden_week(group_rbac: str, project: str, week_start: date) -> tuple[int, Decimal]:
    """Tokens and USD for one group-week, straight from the export files."""
    days = {(week_start.toordinal() + i) for i in range(7)}
    data = REPO_ROOT / "data"

    def in_week(iso: str) -> bool:
        return date.fromisoformat(iso[:10]).toordinal() in days

    usage = json.loads((data / "claude/user_usage_report.json").read_text())["data"]
    cost = json.loads((data / "claude/user_cost_report.json").read_text())["data"]
    gemini = [
        json.loads(line, parse_float=Decimal)
        for line in (data / "gemini/gcp_billing_export_v1_01A2B3_C4D5E6_F7A8B9.jsonl")
        .read_text()
        .splitlines()
    ]
    tokens = sum(
        r["total_tokens"]
        for r in usage
        if r["rbac_group_id"] == group_rbac and in_week(r["starting_at"])
    )
    tokens += int(
        sum(
            r["usage"]["amount"]
            for r in gemini
            if r["project"]["id"] == project and in_week(r["usage_start_time"])
        )
    )
    usd = (
        sum(
            (
                Decimal(r["amount"])
                for r in cost
                if r["rbac_group_id"] == group_rbac and in_week(r["starting_at"])
            ),
            Decimal(0),
        )
        / 100
    )
    usd += sum(
        (
            r["cost"]
            for r in gemini
            if r["project"]["id"] == project and in_week(r["usage_start_time"])
        ),
        Decimal(0),
    )
    return tokens, usd


def test_summary_matches_the_export_files_for_one_group_week(
    clients: dict[str, TestClient],
) -> None:
    status, body = get(clients, "prod", PRIYA, "/usage/summary", period="2026-W36")

    tokens, usd = golden_week(
        "rbac_group_33DEEC83113481C9BD69498282", "meridian-clinops-prod", date(2026, 8, 31)
    )
    assert status == 200
    assert_tool_output("usage_summary", body)
    assert body["group"] == "clinical-operations"  # omitted group = caller's own
    assert body["period"] == {
        "label": "2026-W36",
        "start": "2026-08-31",
        "end_exclusive": "2026-09-07",
        "complete": True,
    }
    assert body["totals"]["total_tokens"] == tokens
    assert body["totals"]["cost_usd"] == round(float(usd), 6)
    gemini = next(p for p in body["platforms"] if p["platform"] == "gemini")
    assert gemini["requests"] is None


def test_team_lead_asking_for_another_group_gets_a_denial_and_no_data(
    clients: dict[str, TestClient],
) -> None:
    status, body = get(clients, "prod", PRIYA, "/usage/summary", period="2026-W36", group="finance")

    assert status == 403
    assert_denial(body)
    assert body == {
        "error": "permission_denied",
        "reason": "Priya Nair may only see their own group (clinical-operations), not 'finance'",
    }
    settings: Settings = clients["prod"].app.state.settings  # type: ignore[attr-defined]
    with closing(sqlite3.connect(settings.database_file)) as conn:
        logged = conn.execute(
            "SELECT caller, action, target_group FROM access_denial ORDER BY id DESC"
        ).fetchone()
    assert logged == (PRIYA, "read_usage", "finance")


def test_member_without_usage_read_is_denied_in_prod_but_not_dev(
    clients: dict[str, TestClient],
) -> None:
    status, body = get(clients, "prod", DANIEL, "/usage/breakdown", period="2026-09")
    assert status == 403 and body["required_scope"] == "usage:read"
    status, body = get(clients, "dev", DANIEL, "/usage/breakdown", period="2026-09", by="group")
    assert status == 200 and len(body["groups"]) == 6


def test_admin_sees_any_group_and_unknown_groups_are_404_for_admins_only(
    clients: dict[str, TestClient],
) -> None:
    assert (
        get(clients, "prod", CHLOE, "/usage/summary", period="2026-09", group="finance")[0] == 200
    )
    assert get(clients, "prod", CHLOE, "/usage/summary", period="2026-09", group="legal")[0] == 404
    assert get(clients, "prod", PRIYA, "/usage/summary", period="2026-09", group="legal")[0] == 403


def test_breakdown_by_group_and_week_adds_up_to_the_whole(clients: dict[str, TestClient]) -> None:
    _, by_group_week = get(
        clients, "prod", CHLOE, "/usage/breakdown", period="last_30_days", by="group,week"
    )
    _, by_platform = get(
        clients, "prod", CHLOE, "/usage/breakdown", period="last_30_days", by="platform"
    )

    assert by_group_week["by"] == ["group", "week"]
    assert {r["group"] for r in by_group_week["rows"]} == set(by_group_week["groups"])
    assert (
        sum(r["total_tokens"] for r in by_group_week["rows"])
        == by_platform["totals"]["total_tokens"]
    )
    assert by_group_week["totals"] == by_platform["totals"]


def test_team_lead_breakdown_without_a_group_covers_only_their_group(
    clients: dict[str, TestClient],
) -> None:
    _, body = get(clients, "prod", PRIYA, "/usage/breakdown", period="2026-09", by="group,model")
    assert body["groups"] == ["clinical-operations"]
    assert {r["group"] for r in body["rows"]} == {"clinical-operations"}
    assert body["period"]["complete"] is False  # data ends 2026-09-27


def test_top_users_are_ranked_and_scoped(clients: dict[str, TestClient]) -> None:
    status, body = get(clients, "prod", PRIYA, "/usage/top-users", period="last_30_days", limit=3)

    assert status == 200
    assert_tool_output("top_users", body)
    assert len(body) == 3
    assert [u["total_tokens"] for u in body] == sorted(
        (u["total_tokens"] for u in body), reverse=True
    )
    assert {u["group"] for u in body} == {"clinical-operations"}


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/usage/summary", {"period": "yesterday"}),
        ("/usage/summary", {"period": "2026-W54"}),
        ("/usage/breakdown", {"period": "2026-09", "by": "user"}),
        ("/usage/breakdown", {"period": "2026-09", "by": "week,week"}),
        ("/usage/top-users", {"period": "2026-09", "limit": 26}),
    ],
)
def test_bad_input_is_422(
    clients: dict[str, TestClient], path: str, params: dict[str, Any]
) -> None:
    assert get(clients, "prod", CHLOE, path, **params)[0] == 422


def test_identity_is_checked_before_input(clients: dict[str, TestClient]) -> None:
    response = clients["prod"].get("/api/v1/usage/summary", params={"period": "2026-W36"})
    assert response.status_code == 401


def test_periods_list_what_the_data_covers(clients: dict[str, TestClient]) -> None:
    body = clients["prod"].get("/api/v1/periods").json()
    assert (body["data_from"], body["data_to_exclusive"]) == ("2026-08-03", "2026-09-28")
    assert body["periods"] == [
        "last_7_days",
        "last_30_days",
        "2026-09",
        "2026-08",
        *[f"2026-W{w}" for w in range(39, 31, -1)],
    ]
