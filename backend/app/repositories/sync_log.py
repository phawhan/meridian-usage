"""Bookkeeping for sync passes (sync_run) and the file versions they take in (source_file)."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.core.clock import utc_now_iso

SourceKind = Literal[
    "directory_users",
    "directory_groups",
    "claude_usage",
    "claude_cost",
    "gemini_billing",
    "environment_config",
]


@dataclass(frozen=True)
class FileCounts:
    rows_read: int | None = None
    rows_inserted: int | None = None
    rows_updated: int | None = None
    rows_deactivated: int | None = None
    rows_quarantined: int | None = None


def start_run(conn: sqlite3.Connection, trigger: Literal["startup", "cli"]) -> int:
    actor = f"system:{trigger}"
    with conn:
        cursor = conn.execute(
            "INSERT INTO sync_run (trigger, status, created_by, updated_by)"
            " VALUES (?, 'running', ?, ?)",
            (trigger, actor, actor),
        )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, error: str | None = None) -> None:
    now = utc_now_iso()
    with conn:
        conn.execute(
            "UPDATE sync_run SET status = ?, error = ?, finished_at = ?, updated_at = ?,"
            " updated_by = created_by WHERE id = ?",
            ("failed" if error else "succeeded", error, now, now, run_id),
        )


def latest_sha256(conn: sqlite3.Connection, path: str) -> str | None:
    """Hash of the most recent version recorded at this path, applied or rejected."""
    row = conn.execute(
        "SELECT sha256 FROM source_file WHERE path = ? ORDER BY id DESC LIMIT 1",
        (path,),
    ).fetchone()
    return row["sha256"] if row else None


def has_applied(conn: sqlite3.Connection, kind: SourceKind) -> bool:
    row = conn.execute(
        "SELECT 1 FROM source_file WHERE source_kind = ? AND status = 'applied' LIMIT 1", (kind,)
    ).fetchone()
    return row is not None


def record_file(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    kind: SourceKind,
    path: str,
    sha256: str,
    exported_at: str | None,
    actor: str,
    error: str | None = None,
) -> int:
    """Insert a source_file row. Callers own the transaction, so an applied file and the
    rows it wrote commit together; a rejected file is committed on its own."""
    cursor = conn.execute(
        "INSERT INTO source_file (sync_run_id, source_kind, path, sha256, exported_at, status,"
        " error, created_by, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            kind,
            path,
            sha256,
            exported_at,
            "rejected" if error else "applied",
            error,
            actor,
            actor,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def set_counts(conn: sqlite3.Connection, file_id: int, counts: FileCounts) -> None:
    conn.execute(
        "UPDATE source_file SET rows_read = ?, rows_inserted = ?, rows_updated = ?,"
        " rows_deactivated = ?, rows_quarantined = ?, updated_at = ? WHERE id = ?",
        (
            counts.rows_read,
            counts.rows_inserted,
            counts.rows_updated,
            counts.rows_deactivated,
            counts.rows_quarantined,
            utc_now_iso(),
            file_id,
        ),
    )


def latest_applied_id(conn: sqlite3.Connection, path: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM source_file WHERE path = ? AND status = 'applied' ORDER BY id DESC LIMIT 1",
        (path,),
    ).fetchone()
    return row["id"] if row else None
