"""Rows -> people and groups, through the directory mirror.

The group comes from the platform's own identifier on the row (Claude rbac_group_id, GCP
project), not from where the person sits today, so history stays true (D6). If the two
disagree the fact is still built, with a group_mismatch warning.
"""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.models.domain import Group, User
from app.repositories import directory
from app.repositories.facts import IssueCode, IssueRow, Platform
from app.repositories.raw import RawTable


@dataclass(frozen=True)
class DirectoryIndex:
    users_by_id: dict[str, User]
    users_by_email: dict[str, User]
    groups_by_rbac_id: dict[str, Group]
    groups_by_project_id: dict[str, Group]

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> "DirectoryIndex":
        users, groups = directory.list_users(conn), directory.list_groups(conn)
        return cls(
            users_by_id={u.user_id: u for u in users},
            users_by_email={u.email: u for u in users},
            groups_by_rbac_id={g.claude_rbac_group_id: g for g in groups},
            groups_by_project_id={g.gcp_project_id: g for g in groups},
        )


@dataclass(frozen=True)
class Context:
    platform: Platform
    usage_date: str
    raw_table: RawTable
    raw_ids: tuple[int, ...]

    def issue(
        self, severity: Literal["error", "warning"], code: IssueCode, detail: str
    ) -> IssueRow:
        return IssueRow(
            platform=self.platform,
            usage_date=self.usage_date,
            severity=severity,
            code=code,
            detail=detail,
            raw_table=self.raw_table,
            raw_ids=self.raw_ids,
        )


@dataclass(frozen=True)
class Attribution:
    user_id: str
    group_id: str


def attribute(
    context: Context,
    *,
    user: User | None,
    user_ref: str,
    group: Group | None,
    group_ref: str,
) -> tuple[Attribution | None, list[IssueRow]]:
    """Errors exclude the row from totals; a mismatch is only a warning."""
    errors = []
    if user is None:
        errors.append(context.issue("error", "unknown_user", f"no directory user for {user_ref}"))
    if group is None:
        errors.append(
            context.issue("error", "unknown_group", f"no directory group for {group_ref}")
        )
    if user is None or group is None:
        return None, errors
    warnings = []
    if group.group_id not in user.group_ids:
        warnings.append(
            context.issue(
                "warning",
                "group_mismatch",
                f"{user.user_id} is in {user.group_ids or 'no group'} but {group_ref} maps to"
                f" {group.group_id}; attributed to {group.group_id}",
            )
        )
    return Attribution(user.user_id, group.group_id), warnings
