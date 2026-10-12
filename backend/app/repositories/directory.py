"""Read and write the directory mirror (groups, users, user_groups).

Writes are called only by the directory sync service inside its transaction.
"""

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Literal

from app.models.domain import Group, User
from app.repositories.sync_log import FileCounts

SYNC_ACTOR = "system:directory-sync"

Record = Mapping[str, object]


def upsert_snapshot(
    conn: sqlite3.Connection,
    table: Literal["groups", "users"],
    key: Literal["group_id", "user_id"],
    records: Sequence[Record],
    *,
    file_id: int,
    now: str,
) -> FileCounts:
    """Insert new rows, update changed or returning rows, deactivate rows missing from the
    snapshot (D14). Unchanged rows aren't touched, so source_file_id and updated_at keep
    pointing at the version that last changed them."""
    existing = {row[key]: row for row in conn.execute(f"SELECT * FROM {table}")}
    inserted = updated = 0
    for record in records:
        columns = list(record)
        current = existing.get(record[key])
        if current is None:
            names = ", ".join(
                [*columns, "source_file_id", "created_at", "created_by", "updated_at", "updated_by"]
            )
            marks = ", ".join("?" * (len(columns) + 5))
            conn.execute(
                f"INSERT INTO {table} ({names}) VALUES ({marks})",
                (*record.values(), file_id, now, SYNC_ACTOR, now, SYNC_ACTOR),
            )
            inserted += 1
        elif current["deactivated_at"] is not None or any(current[c] != record[c] for c in columns):
            assignments = ", ".join(f"{c} = ?" for c in columns if c != key)
            values = [record[c] for c in columns if c != key]
            conn.execute(
                f"UPDATE {table} SET {assignments}, deactivated_at = NULL, source_file_id = ?,"
                f" updated_at = ?, updated_by = ? WHERE {key} = ?",
                (*values, file_id, now, SYNC_ACTOR, record[key]),
            )
            updated += 1

    seen = {record[key] for record in records}
    missing = [k for k, row in existing.items() if row["deactivated_at"] is None and k not in seen]
    conn.executemany(
        f"UPDATE {table} SET deactivated_at = ?, source_file_id = ?, updated_at = ?,"
        f" updated_by = ? WHERE {key} = ?",
        [(now, file_id, now, SYNC_ACTOR, k) for k in missing],
    )
    return FileCounts(
        rows_read=len(records),
        rows_inserted=inserted,
        rows_updated=updated,
        rows_deactivated=len(missing),
    )


def sync_memberships(conn: sqlite3.Connection, desired: set[tuple[str, str]], now: str) -> None:
    """Apply only the membership differences, so created_at keeps meaning "member since"."""
    current = {
        (row["user_id"], row["group_id"])
        for row in conn.execute("SELECT user_id, group_id FROM user_groups")
    }
    conn.executemany(
        "DELETE FROM user_groups WHERE user_id = ? AND group_id = ?", sorted(current - desired)
    )
    conn.executemany(
        "INSERT INTO user_groups (user_id, group_id, created_at, created_by) VALUES (?, ?, ?, ?)",
        [(u, g, now, SYNC_ACTOR) for u, g in sorted(desired - current)],
    )


# --- Reads -----------------------------------------------------------------------------

_USER_SELECT = """
    SELECT u.user_id, u.email, u.name, u.role, u.deactivated_at,
           (SELECT json_group_array(ug.group_id) FROM user_groups ug
             WHERE ug.user_id = u.user_id) AS group_ids
      FROM users u
"""

_GROUP_SELECT = """
    SELECT group_id, name, team_lead_user_id, claude_rbac_group_id, gcp_project_id,
           cost_centre, deactivated_at
      FROM groups
"""


def _user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        user_id=row["user_id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        group_ids=sorted(json.loads(row["group_ids"])),
        active=row["deactivated_at"] is None,
    )


def _group(row: sqlite3.Row | None) -> Group | None:
    if row is None:
        return None
    return Group(
        group_id=row["group_id"],
        name=row["name"],
        team_lead_user_id=row["team_lead_user_id"],
        claude_rbac_group_id=row["claude_rbac_group_id"],
        gcp_project_id=row["gcp_project_id"],
        cost_centre=row["cost_centre"],
        active=row["deactivated_at"] is None,
    )


def get_user(conn: sqlite3.Connection, user_id: str) -> User | None:
    return _user(conn.execute(f"{_USER_SELECT} WHERE u.user_id = ?", (user_id,)).fetchone())


def get_user_by_email(conn: sqlite3.Connection, email: str) -> User | None:
    row = conn.execute(f"{_USER_SELECT} WHERE u.email = ?", (email.strip().lower(),)).fetchone()
    return _user(row)


def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(f"{_USER_SELECT} ORDER BY u.name").fetchall()
    return [user for row in rows if (user := _user(row)) is not None]


def get_group(conn: sqlite3.Connection, group_id: str) -> Group | None:
    return _group(conn.execute(f"{_GROUP_SELECT} WHERE group_id = ?", (group_id,)).fetchone())


def get_group_by_rbac_id(conn: sqlite3.Connection, rbac_group_id: str) -> Group | None:
    row = conn.execute(f"{_GROUP_SELECT} WHERE claude_rbac_group_id = ?", (rbac_group_id,))
    return _group(row.fetchone())


def get_group_by_project_id(conn: sqlite3.Connection, gcp_project_id: str) -> Group | None:
    row = conn.execute(f"{_GROUP_SELECT} WHERE gcp_project_id = ?", (gcp_project_id,))
    return _group(row.fetchone())


def list_groups(conn: sqlite3.Connection) -> list[Group]:
    rows = conn.execute(f"{_GROUP_SELECT} ORDER BY group_id").fetchall()
    return [group for row in rows if (group := _group(row)) is not None]
