import json
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import PolicyError, load_policy
from app.db.session import connect, init_db
from app.services import capabilities
from app.services.sync import run_sync

CHLOE = "user_533B58E6F66C98ACB833527A"  # platform admin


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shutil.copytree(REPO_ROOT / "data" / "directory", tmp_path / "data" / "directory")
    shutil.copytree(REPO_ROOT / "environments", tmp_path / "environments")
    return Settings(
        app_env="prod",
        db_path=tmp_path / "prod.db",
        data_dir=tmp_path / "data",
        env_dir=tmp_path / "environments",
    )


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = connect(settings.database_file)
    init_db(connection, "prod")
    yield connection
    connection.close()


def switch(conn: sqlite3.Connection, group: str, capability: str) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM capability_state WHERE group_id = ? AND capability = ?",
        (group, capability),
    ).fetchone()
    assert row is not None
    return row


def test_fresh_prod_database_matches_the_baseline(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    report = run_sync(conn, settings, load_policy(settings), trigger="startup")

    assert report.switches_seeded == 18  # 6 groups x 3 capabilities
    enabled = {
        (r["group_id"], r["capability"])
        for r in conn.execute("SELECT * FROM capability_state WHERE enabled = 1")
    }
    connector_on = {g for g, c in enabled if c == "usage-connector"}
    assert connector_on == {"it-platform", "clinical-operations"}
    assert not any(c == "code-execution" for _, c in enabled)
    assert sum(1 for _, c in enabled if c == "web-search") == 6
    seed = conn.execute("SELECT * FROM capability_audit LIMIT 1").fetchone()
    policy_file = conn.execute(
        "SELECT * FROM source_file WHERE id = ?", (seed["policy_file_id"],)
    ).fetchone()
    assert (seed["action"], seed["old_enabled"], seed["created_by"]) == (
        "seed",
        None,
        "system:startup",
    )
    assert (policy_file["source_kind"], policy_file["path"]) == (
        "environment_config",
        "environments/prod.yaml",
    )


def test_a_change_survives_restart_and_is_audited(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    policy = load_policy(settings)
    report = run_sync(conn, settings, policy, trigger="startup")

    state = capabilities.change(
        conn,
        policy,
        report.policy_file_id,
        group_id="finance",
        capability="usage-connector",
        enabled=True,
        actor=CHLOE,
    )
    restart = run_sync(conn, settings, load_policy(settings), trigger="startup")

    assert state.enabled and state.drift and state.updated_by == CHLOE
    assert restart.switches_seeded == 0
    assert switch(conn, "finance", "usage-connector")["enabled"] == 1
    audit = conn.execute("SELECT * FROM capability_audit WHERE action = 'set'").fetchall()
    assert [(a["old_enabled"], a["new_enabled"], a["created_by"]) for a in audit] == [(0, 1, CHLOE)]


def test_setting_the_same_value_changes_nothing(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    policy = load_policy(settings)
    report = run_sync(conn, settings, policy, trigger="startup")
    before = switch(conn, "finance", "web-search")

    state = capabilities.change(
        conn,
        policy,
        report.policy_file_id,
        group_id="finance",
        capability="web-search",
        enabled=True,
        actor=CHLOE,
    )

    assert state.enabled and not state.drift
    assert switch(conn, "finance", "web-search")["updated_at"] == before["updated_at"]
    assert (
        conn.execute("SELECT COUNT(*) FROM capability_audit WHERE action != 'seed'").fetchone()[0]
        == 0
    )


def test_reset_returns_to_the_baseline(conn: sqlite3.Connection, settings: Settings) -> None:
    policy = load_policy(settings)
    report = run_sync(conn, settings, policy, trigger="startup")
    args = dict(group_id="finance", capability="usage-connector", actor=CHLOE)
    capabilities.change(conn, policy, report.policy_file_id, enabled=True, **args)  # type: ignore[arg-type]

    state = capabilities.change(conn, policy, report.policy_file_id, enabled=None, **args)  # type: ignore[arg-type]

    assert not state.enabled and not state.drift
    last = conn.execute("SELECT * FROM capability_audit ORDER BY id DESC").fetchone()
    assert (last["action"], last["old_enabled"], last["new_enabled"]) == ("reset", 1, 0)


def test_policy_change_is_recorded_and_new_audit_rows_point_at_it(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    first = run_sync(conn, settings, load_policy(settings), trigger="startup")
    prod_yaml = settings.env_dir / "prod.yaml"
    prod_yaml.write_text(
        prod_yaml.read_text().replace(
            "roles: [platform_admin]", "roles: [platform_admin, team_lead]"
        )
    )
    policy = load_policy(settings)

    second = run_sync(conn, settings, policy, trigger="startup")
    capabilities.change(
        conn,
        policy,
        second.policy_file_id,
        group_id="hr",
        capability="web-search",
        enabled=False,
        actor=CHLOE,
    )

    assert second.policy_file_id != first.policy_file_id
    last = conn.execute("SELECT * FROM capability_audit ORDER BY id DESC").fetchone()
    assert last["policy_file_id"] == second.policy_file_id


def test_new_group_in_directory_is_seeded_from_the_baseline(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, load_policy(settings), trigger="startup")
    users_path = settings.data_dir / "directory" / "users.json"
    groups_path = settings.data_dir / "directory" / "groups.json"
    users, groups = json.loads(users_path.read_text()), json.loads(groups_path.read_text())
    groups["groups"].append(
        groups["groups"][0]
        | {
            "group_id": "legal",
            "name": "Legal",
            "team_lead_user_id": "user_LEGAL",
            "claude_rbac_group_id": "rbac_legal",
            "gcp_project_id": "meridian-legal-prod",
        }
    )
    users["users"].append(
        users["users"][0]
        | {"user_id": "user_LEGAL", "email": "lead@legal.example", "group_ids": ["legal"]}
    )
    users_path.write_text(json.dumps(users))
    groups_path.write_text(json.dumps(groups))

    report = run_sync(conn, settings, load_policy(settings), trigger="startup")

    assert report.switches_seeded == 3
    assert (
        switch(conn, "legal", "usage-connector")["enabled"] == 0
    )  # prod: disabled until requested


def test_baseline_naming_an_unknown_group_refuses_to_start(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    prod_yaml = settings.env_dir / "prod.yaml"
    prod_yaml.write_text(
        prod_yaml.read_text().replace("clinical-operations]", "clinical-operation]")
    )

    with pytest.raises(PolicyError, match="clinical-operation"):
        run_sync(conn, settings, load_policy(settings), trigger="startup")
    assert conn.execute("SELECT COUNT(*) FROM capability_state").fetchone()[0] == 0
