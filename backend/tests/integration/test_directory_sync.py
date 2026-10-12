import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import REPO_ROOT, Settings
from app.db.session import connect, init_db
from app.repositories import directory
from app.services.sync import DirectoryUnavailableError, run_sync

DANIEL = "user_699C48763F6FA2958D2CDB5D"  # member of clinical-operations
PRIYA = "user_E7691888F28227066DD2FB86"  # team lead of clinical-operations

Mutation = Callable[[dict[str, Any]], None]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    shutil.copytree(REPO_ROOT / "data" / "directory", data_dir / "directory")
    return Settings(app_env="dev", db_path=tmp_path / "test.db", data_dir=data_dir)


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = connect(settings.database_file)
    init_db(connection, "dev")
    yield connection
    connection.close()


def edit(settings: Settings, name: str, mutate: Mutation) -> None:
    path = settings.data_dir / "directory" / name
    content = json.loads(path.read_text())
    mutate(content)
    path.write_text(json.dumps(content, indent=2))


def drop_daniel(users: dict[str, Any]) -> None:
    users["users"] = [u for u in users["users"] if u["user_id"] != DANIEL]


def count(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def test_first_sync_mirrors_the_snapshot_with_audit_columns(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    report = run_sync(conn, settings, trigger="cli")

    assert report.directory.status == "applied"
    assert report.directory.users and report.directory.users.rows_inserted == 22
    assert report.directory.groups and report.directory.groups.rows_inserted == 6
    assert count(conn, "SELECT COUNT(*) FROM users WHERE deactivated_at IS NULL") == 22
    assert count(conn, "SELECT COUNT(*) FROM user_groups") == 22
    files = conn.execute("SELECT source_kind, path, status FROM source_file ORDER BY id").fetchall()
    assert [tuple(f) for f in files] == [
        ("directory_users", "data/directory/users.json", "applied"),
        ("directory_groups", "data/directory/groups.json", "applied"),
    ]
    priya = conn.execute("SELECT * FROM users WHERE user_id = ?", (PRIYA,)).fetchone()
    assert priya["created_by"] == priya["updated_by"] == "system:directory-sync"
    assert priya["created_at"].endswith("Z")
    run = conn.execute("SELECT * FROM sync_run").fetchone()
    assert (run["trigger"], run["status"], run["created_by"]) == ("cli", "succeeded", "system:cli")


def test_unchanged_snapshot_records_nothing_new(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, trigger="cli")
    report = run_sync(conn, settings, trigger="cli")

    assert report.directory.status == "unchanged"
    assert count(conn, "SELECT COUNT(*) FROM source_file") == 2
    assert count(conn, "SELECT COUNT(*) FROM sync_run") == 2


def test_leaver_is_deactivated_not_deleted(conn: sqlite3.Connection, settings: Settings) -> None:
    run_sync(conn, settings, trigger="cli")
    first_users_file = conn.execute("SELECT source_file_id FROM users WHERE user_id = ?", (PRIYA,))
    first_id = first_users_file.fetchone()[0]
    edit(settings, "users.json", drop_daniel)

    report = run_sync(conn, settings, trigger="cli")

    assert report.directory.users is not None
    assert (report.directory.users.rows_deactivated, report.directory.users.rows_updated) == (1, 0)
    daniel = directory.get_user(conn, DANIEL)
    assert daniel is not None and not daniel.active and daniel.group_ids == []
    # Unchanged rows still point at the file version that last changed them.
    priya_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (PRIYA,)).fetchone()
    assert priya_row["source_file_id"] == first_id


def test_redelivered_older_snapshot_rolls_back(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    original = (settings.data_dir / "directory" / "users.json").read_bytes()
    run_sync(conn, settings, trigger="cli")
    edit(settings, "users.json", drop_daniel)
    run_sync(conn, settings, trigger="cli")
    (settings.data_dir / "directory" / "users.json").write_bytes(original)

    report = run_sync(conn, settings, trigger="cli")

    assert report.directory.status == "applied"
    daniel = directory.get_user(conn, DANIEL)
    assert daniel is not None and daniel.active and daniel.group_ids == ["clinical-operations"]


def test_changed_field_updates_row_and_keeps_created_at(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, trigger="cli")
    before = conn.execute("SELECT * FROM users WHERE user_id = ?", (DANIEL,)).fetchone()

    def rename(users: dict[str, Any]) -> None:
        next(u for u in users["users"] if u["user_id"] == DANIEL)["name"] = "Dan Okafor"

    edit(settings, "users.json", rename)
    report = run_sync(conn, settings, trigger="cli")

    after = conn.execute("SELECT * FROM users WHERE user_id = ?", (DANIEL,)).fetchone()
    assert report.directory.users is not None and report.directory.users.rows_updated == 1
    assert after["name"] == "Dan Okafor"
    assert after["created_at"] == before["created_at"]
    assert after["source_file_id"] != before["source_file_id"]


def test_invalid_snapshot_is_rejected_once_and_old_mirror_kept(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, trigger="cli")

    def demote_priya(users: dict[str, Any]) -> None:
        next(u for u in users["users"] if u["user_id"] == PRIYA)["role"] = "member"

    edit(settings, "users.json", demote_priya)
    report = run_sync(conn, settings, trigger="cli")
    again = run_sync(conn, settings, trigger="cli")

    assert report.directory.status == "rejected"
    assert again.directory.status == "unchanged"  # same bytes, same verdict, logged once
    rejected = conn.execute("SELECT * FROM source_file WHERE status = 'rejected'").fetchall()
    assert len(rejected) == 2 and "has role member" in rejected[0]["error"]
    priya = directory.get_user(conn, PRIYA)
    assert priya is not None and priya.role == "team_lead"
    runs = [r["status"] for r in conn.execute("SELECT status FROM sync_run ORDER BY id")]
    assert runs == ["succeeded", "failed", "succeeded"]


def test_malformed_file_is_rejected_with_field_detail(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, trigger="cli")
    edit(settings, "users.json", lambda users: users["users"][0].update(role="superuser"))

    report = run_sync(conn, settings, trigger="cli")

    assert report.directory.status == "rejected"
    assert any("users.0.role" in e for e in report.directory.errors)


def test_no_valid_snapshot_ever_refuses_to_start(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    edit(settings, "groups.json", lambda groups: groups.update(groups=[]))

    with pytest.raises(DirectoryUnavailableError, match="no groups"):
        run_sync(conn, settings, trigger="startup")
    assert conn.execute("SELECT status FROM sync_run").fetchone()[0] == "failed"


def test_lookups_resolve_platform_identifiers(conn: sqlite3.Connection, settings: Settings) -> None:
    run_sync(conn, settings, trigger="cli")

    by_email = directory.get_user_by_email(conn, " Priya.Nair@MeridianLS.example")
    by_rbac = directory.get_group_by_rbac_id(conn, "rbac_group_33DEEC83113481C9BD69498282")
    by_project = directory.get_group_by_project_id(conn, "meridian-clinops-prod")

    assert by_email is not None and by_email.user_id == PRIYA
    assert by_rbac is not None and by_rbac.group_id == "clinical-operations"
    assert by_project is not None and by_project.group_id == "clinical-operations"
    assert directory.get_user(conn, "user_nobody") is None
    assert len(directory.list_users(conn)) == 22
    assert [g.group_id for g in directory.list_groups(conn)][0] == "clinical-operations"
