import sqlite3
from typing import Literal

AuditAction = Literal["seed", "set", "reset"]


def existing(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    return {
        (r["group_id"], r["capability"]) for r in conn.execute("SELECT * FROM capability_state")
    }


def rows(conn: sqlite3.Connection, group_ids: list[str]) -> list[sqlite3.Row]:
    marks = ", ".join("?" * len(group_ids))
    return conn.execute(
        f"SELECT * FROM capability_state WHERE group_id IN ({marks}) ORDER BY group_id, capability",
        group_ids,
    ).fetchall()


def get(conn: sqlite3.Connection, group_id: str, capability: str) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM capability_state WHERE group_id = ? AND capability = ?",
        (group_id, capability),
    ).fetchone()
    return row


def insert(
    conn: sqlite3.Connection, group_id: str, capability: str, enabled: bool, actor: str, now: str
) -> None:
    conn.execute(
        "INSERT INTO capability_state (group_id, capability, enabled, created_at, created_by,"
        " updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (group_id, capability, int(enabled), now, actor, now, actor),
    )


def update(
    conn: sqlite3.Connection, group_id: str, capability: str, enabled: bool, actor: str, now: str
) -> None:
    conn.execute(
        "UPDATE capability_state SET enabled = ?, updated_at = ?, updated_by = ?"
        " WHERE group_id = ? AND capability = ?",
        (int(enabled), now, actor, group_id, capability),
    )


def audit(
    conn: sqlite3.Connection,
    *,
    group_id: str,
    capability: str,
    action: AuditAction,
    old: bool | None,
    new: bool,
    policy_file_id: int,
    actor: str,
    now: str,
) -> None:
    conn.execute(
        "INSERT INTO capability_audit (group_id, capability, action, old_enabled, new_enabled,"
        " policy_file_id, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            group_id,
            capability,
            action,
            None if old is None else int(old),
            int(new),
            policy_file_id,
            now,
            actor,
        ),
    )


def history(conn: sqlite3.Connection, group_ids: list[str], limit: int = 100) -> list[sqlite3.Row]:
    marks = ", ".join("?" * len(group_ids))
    return conn.execute(
        f"SELECT * FROM capability_audit WHERE group_id IN ({marks}) ORDER BY id DESC LIMIT ?",
        [*group_ids, limit],
    ).fetchall()
