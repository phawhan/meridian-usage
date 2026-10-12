import json
import shutil
import sqlite3
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import load_policy
from app.db.session import connect, init_db
from app.services.sync import run_sync

GEMINI_FILE = "gcp_billing_export_v1_01A2B3_C4D5E6_F7A8B9.jsonl"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shutil.copytree(REPO_ROOT / "data", tmp_path / "data")
    return Settings(app_env="dev", db_path=tmp_path / "test.db", data_dir=tmp_path / "data")


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = connect(settings.database_file)
    init_db(connection, "dev")
    yield connection
    connection.close()


def gemini_rows(settings: Settings) -> list[dict[str, Any]]:
    lines = (settings.data_dir / "gemini" / GEMINI_FILE).read_text().splitlines()
    return [json.loads(line, parse_float=Decimal) for line in lines if line.strip()]


def write_gemini(settings: Settings, name: str, rows: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(r, default=str) for r in rows)
    # default=str writes Decimals as strings; turn cost back into a JSON number.
    for r in rows:
        text = text.replace(f'"cost": "{r["cost"]}"', f'"cost": {r["cost"]}', 1)
    (settings.data_dir / "gemini" / name).write_text(text + "\n")


def totals(conn: sqlite3.Connection, platform: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT SUM(total_tokens), SUM(cost_nanousd) FROM usage_fact WHERE platform = ?",
        (platform,),
    ).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def test_facts_reconcile_with_the_source_files(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    """Golden totals computed straight from the exports, independently of the pipeline.
    Catches any row dropped, double counted or mis-converted."""
    claude_usage = json.loads((settings.data_dir / "claude/user_usage_report.json").read_text())
    claude_cost = json.loads((settings.data_dir / "claude/user_cost_report.json").read_text())
    gemini = gemini_rows(settings)

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    assert report.ok and report.usage.errors == 0 and report.usage.warnings == 0
    assert totals(conn, "claude") == (
        sum(r["total_tokens"] for r in claude_usage["data"]),
        int(sum(Decimal(r["amount"]) for r in claude_cost["data"]) * 10**7),
    )
    assert totals(conn, "gemini") == (
        int(sum(r["usage"]["amount"] for r in gemini)),
        int(sum(r["cost"] for r in gemini) * 10**9),
    )
    assert conn.execute("SELECT COUNT(*) FROM usage_fact").fetchone()[0] == 1346 + 990 // 2
    weeks = [r[0] for r in conn.execute("SELECT DISTINCT iso_week FROM usage_fact ORDER BY 1")]
    assert weeks == [f"2026-W{w}" for w in range(32, 40)]


def test_every_raw_row_is_in_a_fact_or_an_issue(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, load_policy(settings), trigger="cli")
    for table in ("raw_claude_usage", "raw_claude_cost", "raw_gemini_billing"):
        raw_ids = {r[0] for r in conn.execute(f"SELECT id FROM {table}")}
        in_facts = {
            int(j[0])
            for j in conn.execute(
                "SELECT j.value FROM usage_fact f, json_each(f.raw_refs, ?) j", (f"$.{table}",)
            )
        }
        in_issues = {
            int(j[0])
            for j in conn.execute(
                "SELECT j.value FROM ingest_issue i, json_each(i.raw_ids) j WHERE raw_table = ?",
                (table,),
            )
        }
        assert raw_ids == in_facts | in_issues, table


def test_second_pass_changes_nothing(conn: sqlite3.Connection, settings: Settings) -> None:
    run_sync(conn, settings, load_policy(settings), trigger="cli")
    before = totals(conn, "claude"), totals(conn, "gemini")

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    assert {f.status for f in report.usage.files} == {"unchanged"}
    assert report.usage.partitions_rebuilt == 0
    assert (totals(conn, "claude"), totals(conn, "gemini")) == before


def test_delta_file_with_a_newer_correction_rebuilds_only_its_day(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, load_policy(settings), trigger="cli")
    _, cost_before = totals(conn, "gemini")
    corrected = gemini_rows(settings)[0]
    old_cost = corrected["cost"]
    corrected["cost"] = old_cost + Decimal("1.5")
    corrected["export_time"] = "2026-10-01 00:00:00 UTC"  # newer than the original
    write_gemini(settings, "gcp_billing_export_v1_delta_20261001.jsonl", [corrected])

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    delta = next(f for f in report.usage.files if "delta" in f.path)
    assert delta.counts is not None and (delta.counts.rows_inserted, delta.counts.rows_updated) == (
        0,
        1,
    )
    assert report.usage.partitions_rebuilt == 1
    assert totals(conn, "gemini")[1] == cost_before + 1_500_000_000


def test_older_export_arriving_later_does_not_overwrite(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    run_sync(conn, settings, load_policy(settings), trigger="cli")
    before = totals(conn, "gemini")
    stale = gemini_rows(settings)[0]
    stale["cost"] = Decimal("999")
    stale["export_time"] = "2026-08-01 00:00:00 UTC"  # older than what we hold
    write_gemini(settings, "gcp_billing_export_v1_stale.jsonl", [stale])

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    stale_file = next(f for f in report.usage.files if "stale" in f.path)
    assert stale_file.counts is not None and stale_file.counts.rows_updated == 0
    assert totals(conn, "gemini") == before


def test_unknown_owner_is_quarantined_then_recovered_when_directory_catches_up(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    rows = gemini_rows(settings)
    for row in rows[:2]:
        row["labels"] = [lbl for lbl in row["labels"] if lbl["key"] != "owner"]
        row["labels"].append({"key": "owner", "value": "new.hire@meridianls.example"})
    write_gemini(settings, GEMINI_FILE, rows)

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")
    issue = conn.execute("SELECT * FROM ingest_issue").fetchone()
    assert report.usage.errors == 1 and issue["code"] == "unknown_user"
    assert "new.hire@meridianls.example" in issue["detail"]
    gemini = next(f for f in report.usage.files if f.path.endswith(GEMINI_FILE))
    assert gemini.counts is not None and gemini.counts.rows_quarantined == 2

    users_path = settings.data_dir / "directory" / "users.json"
    users = json.loads(users_path.read_text())
    users["users"].append(
        users["users"][1]
        | {"user_id": "user_NEWHIRE", "email": "new.hire@meridianls.example", "name": "New Hire"}
    )
    users_path.write_text(json.dumps(users))
    recovered = run_sync(conn, settings, load_policy(settings), trigger="cli")

    assert recovered.usage.errors == 0
    assert conn.execute("SELECT COUNT(*) FROM ingest_issue").fetchone()[0] == 0
    assert (
        conn.execute("SELECT COUNT(*) FROM usage_fact WHERE user_id = 'user_NEWHIRE'").fetchone()[0]
        == 1
    )


def test_file_with_duplicate_keys_is_rejected_whole_and_others_still_load(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    row = gemini_rows(settings)[0]
    write_gemini(settings, "gcp_billing_export_v1_dupe.jsonl", [row, row])

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    dupe = next(f for f in report.usage.files if "dupe" in f.path)
    assert dupe.status == "rejected" and dupe.error and "appear twice" in dupe.error
    assert not report.ok
    assert conn.execute("SELECT status FROM sync_run").fetchone()[0] == "failed"
    assert conn.execute("SELECT COUNT(*) FROM usage_fact").fetchone()[0] == 1841


def test_malformed_line_rejects_the_file_with_its_line_number(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    (settings.data_dir / "gemini" / "gcp_billing_export_v1_bad.jsonl").write_text('{"cost": 1}\n')

    report = run_sync(conn, settings, load_policy(settings), trigger="cli")

    bad = next(f for f in report.usage.files if "bad" in f.path)
    assert bad.status == "rejected" and bad.error and bad.error.startswith("line 1:")
