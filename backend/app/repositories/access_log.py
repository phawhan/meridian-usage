import sqlite3
from typing import Literal


def record(
    conn: sqlite3.Connection,
    *,
    channel: Literal["api", "connector"],
    caller: str | None,
    action: str,
    target_group: str | None,
    required_scope: str | None,
    reason: str,
) -> None:
    """Committed on its own: the refusal is recorded even though the request fails."""
    with conn:
        conn.execute(
            "INSERT INTO access_denial (channel, caller, action, target_group, required_scope,"
            " reason, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (channel, caller, action, target_group, required_scope, reason, f"system:{channel}"),
        )
