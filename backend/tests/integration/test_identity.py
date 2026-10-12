import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Settings
from app.main import create_app

DANIEL = "user_699C48763F6FA2958D2CDB5D"  # member, clinical-operations
PRIYA = "user_E7691888F28227066DD2FB86"  # team lead, clinical-operations
CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin, it-platform
ALL_GROUPS = [
    "clinical-operations",
    "finance",
    "hr",
    "it-platform",
    "medical-writing",
    "regulatory-affairs",
]

ClientFactory = Callable[[str], TestClient]


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[ClientFactory]:
    # Directory only: identity tests don't need usage ingestion.
    shutil.copytree(REPO_ROOT / "data" / "directory", tmp_path / "data" / "directory")
    clients: list[TestClient] = []

    def make(env: str) -> TestClient:
        settings = Settings(app_env=env, db_path=tmp_path / f"{env}.db", data_dir=tmp_path / "data")  # type: ignore[arg-type]
        client = TestClient(create_app(settings))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def denials(client: TestClient) -> list[tuple[str | None, str]]:
    import sqlite3
    from contextlib import closing

    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    with closing(sqlite3.connect(settings.database_file)) as conn:
        rows = conn.execute("SELECT caller, action FROM access_denial ORDER BY id").fetchall()
    return [(r[0], r[1]) for r in rows]


def test_no_identity_is_401_and_logged(make_client: ClientFactory) -> None:
    client = make_client("prod")
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": "unauthenticated",
        "reason": "send the X-User-Id header with a directory user_id",
    }
    assert denials(client) == [(None, "identify")]


def test_unknown_user_is_401(make_client: ClientFactory) -> None:
    client = make_client("prod")
    response = client.get("/api/v1/me", headers={"X-User-Id": "user_nobody"})
    assert response.status_code == 401
    assert "'user_nobody' is not an active user" in response.json()["reason"]


@pytest.mark.parametrize(
    ("env", "user", "scopes", "readable", "writable"),
    [
        ("prod", DANIEL, [], [], []),
        ("prod", PRIYA, ["usage:read"], ["clinical-operations"], []),
        ("prod", CHLOE, ["usage:read", "capabilities:write"], ALL_GROUPS, ALL_GROUPS),
        (
            "staging",
            PRIYA,
            ["usage:read", "capabilities:write"],
            ["clinical-operations"],
            ["clinical-operations"],
        ),
        ("dev", DANIEL, ["usage:read"], ALL_GROUPS, []),
        ("dev", PRIYA, ["usage:read", "capabilities:write"], ALL_GROUPS, ["clinical-operations"]),
    ],
)
def test_me_reports_what_the_policy_allows(
    make_client: ClientFactory,
    env: str,
    user: str,
    scopes: list[str],
    readable: list[str],
    writable: list[str],
) -> None:
    body = make_client(env).get("/api/v1/me", headers={"X-User-Id": user}).json()
    assert body["environment"] == env
    assert body["scopes"] == scopes
    assert body["readable_groups"] == readable
    assert body["writable_groups"] == writable


def test_someone_who_left_is_401(make_client: ClientFactory, tmp_path: Path) -> None:
    import json

    users_path = tmp_path / "data" / "directory" / "users.json"
    users = json.loads(users_path.read_text())
    users["users"] = [u for u in users["users"] if u["user_id"] != DANIEL]
    make_client("dev").__exit__(None, None, None)  # first start: Daniel active
    users_path.write_text(json.dumps(users))

    client = make_client("dev")  # restart: Daniel deactivated, row kept
    response = client.get("/api/v1/me", headers={"X-User-Id": DANIEL})
    assert response.status_code == 401
