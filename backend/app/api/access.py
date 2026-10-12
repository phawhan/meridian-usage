"""Which groups a request covers. Every route resolves its groups here, so the visibility
rule from services.authz is applied the same way everywhere."""

import sqlite3

from fastapi import HTTPException

from app.core.env_config import Policy
from app.models.domain import User
from app.repositories import directory
from app.services.authz import Action, enforce, visible_groups


def _active_groups(conn: sqlite3.Connection) -> list[str]:
    return [g.group_id for g in directory.list_groups(conn) if g.active]


def one_group(
    conn: sqlite3.Connection, caller: User, action: Action, policy: Policy, requested: str | None
) -> str:
    """The group asked for, or the caller's own group when none is given (tool contract)."""
    group = requested or (caller.group_ids[0] if caller.group_ids else "")
    enforce(conn, caller, action, group, policy)  # 403 + logged; unknown groups too, for non-admins
    if group not in _active_groups(conn):
        raise HTTPException(status_code=404, detail=f"no group '{group}'")
    return group


def many_groups(
    conn: sqlite3.Connection, caller: User, action: Action, policy: Policy, requested: str | None
) -> list[str]:
    """The group asked for, or every group the caller may see when none is given."""
    if requested is not None:
        return [one_group(conn, caller, action, policy, requested)]
    groups = visible_groups(caller, action, policy, _active_groups(conn))
    if not groups:  # lacks the scope entirely: refuse (and log) rather than return nothing
        enforce(conn, caller, action, caller.group_ids[0] if caller.group_ids else "", policy)
    return groups
