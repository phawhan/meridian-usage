"""Every access decision in the service is made here, and only here.

authorize() is pure: caller + action + group + policy -> allowed or a Denial. It reads the
rules from the environment policy and never from a prompt, a request body or a database
table a caller can write to. enforce() wraps it for request handlers and logs refusals.

Rules, in order:
  1. The caller's role must hold the scope the action needs in this environment.
  2. Reads: any group when the scope's visibility is 'all'; otherwise the caller's own
     groups, except platform admins, who see every group.
  3. Writes: platform admins any group; everyone else only their own groups (D2).
A group that doesn't exist is refused like someone else's group, for non-admins, so a
caller can't probe which groups exist.
"""

import sqlite3
from typing import Literal

from app.core.env_config import Policy, Scope
from app.models.denial import Denial
from app.models.domain import User
from app.repositories import access_log

Action = Literal["read_usage", "read_capabilities", "write_capability"]
Channel = Literal["api", "connector"]

REQUIRED_SCOPE: dict[Action, Scope] = {
    "read_usage": "usage:read",
    "read_capabilities": "usage:read",
    "write_capability": "capabilities:write",
}


class AccessDenied(Exception):
    def __init__(self, denial: Denial) -> None:
        super().__init__(denial.reason)
        self.denial = denial


def can_see_every_group(caller: User, action: Action, policy: Policy) -> bool:
    scope = REQUIRED_SCOPE[action]
    if caller.role not in policy.roles_with(scope):
        return False
    if caller.role == "platform_admin":
        return True
    return action != "write_capability" and policy.scopes[scope].group_visibility == "all"


def authorize(caller: User, action: Action, group_id: str, policy: Policy) -> Denial | None:
    scope = REQUIRED_SCOPE[action]
    if caller.role not in policy.roles_with(scope):
        return Denial(
            reason=f"role '{caller.role}' does not have {scope} in {policy.environment}",
            required_scope=scope,
        )
    if can_see_every_group(caller, action, policy) or group_id in caller.group_ids:
        return None
    verb = "change" if action == "write_capability" else "see"
    return Denial(
        reason=f"{caller.name} may only {verb} their own group"
        f" ({', '.join(caller.group_ids)}), not '{group_id}'",
    )


def visible_groups(
    caller: User, action: Action, policy: Policy, all_groups: list[str]
) -> list[str]:
    """The groups this caller may act on, for listing endpoints. Empty if they lack the scope."""
    return [g for g in all_groups if authorize(caller, action, g, policy) is None]


def enforce(
    conn: sqlite3.Connection,
    caller: User,
    action: Action,
    group_id: str,
    policy: Policy,
    channel: Channel = "api",
) -> None:
    """authorize(), logging and raising on refusal. Request handlers call this."""
    denial = authorize(caller, action, group_id, policy)
    if denial is None:
        return
    access_log.record(
        conn,
        channel=channel,
        caller=caller.user_id,
        action=action,
        target_group=group_id,
        required_scope=denial.required_scope,
        reason=denial.reason,
    )
    raise AccessDenied(denial)
