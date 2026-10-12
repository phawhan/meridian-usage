from typing import Annotated

from fastapi import APIRouter, Query

from app.api.access import many_groups, one_group
from app.api.deps import Caller, CurrentPolicy, Db, PolicyFileId
from app.models.api import AuditEntry, CapabilityChange, CapabilityStatus
from app.models.domain import Capability
from app.repositories import capabilities as repo
from app.services import capabilities
from app.services.capabilities import CapabilityState

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

GroupParam = Annotated[
    str | None, Query(description="group_id; omitted: every group the caller may see")
]


def _out(state: CapabilityState) -> CapabilityStatus:
    return CapabilityStatus(
        group=state.group_id,
        capability=state.capability,
        enabled=state.enabled,
        baseline=state.baseline,
        drift=state.drift,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )


@router.get("", response_model=list[CapabilityStatus])
def list_capabilities(
    caller: Caller, policy: CurrentPolicy, conn: Db, group: GroupParam = None
) -> list[CapabilityStatus]:
    groups = many_groups(conn, caller, "read_capabilities", policy, group)
    return [_out(s) for s in capabilities.states(conn, policy, groups)]


@router.put("/{group}/{capability}", response_model=CapabilityStatus)
def set_capability(
    group: str,
    capability: Capability,
    change: CapabilityChange,
    caller: Caller,
    policy: CurrentPolicy,
    policy_file_id: PolicyFileId,
    conn: Db,
) -> CapabilityStatus:
    """Enable or disable a capability for a group. Needs capabilities:write; team leads may
    only change their own group. Setting the current value again changes nothing."""
    group_id = one_group(conn, caller, "write_capability", policy, group)
    state = capabilities.change(
        conn,
        policy,
        policy_file_id,
        group_id=group_id,
        capability=capability,
        enabled=change.enabled,
        actor=caller.user_id,
    )
    return _out(state)


@router.post("/{group}/{capability}/reset", response_model=CapabilityStatus)
def reset_capability(
    group: str,
    capability: Capability,
    caller: Caller,
    policy: CurrentPolicy,
    policy_file_id: PolicyFileId,
    conn: Db,
) -> CapabilityStatus:
    """Return a switch to this environment's baseline (capability_defaults)."""
    group_id = one_group(conn, caller, "write_capability", policy, group)
    state = capabilities.change(
        conn,
        policy,
        policy_file_id,
        group_id=group_id,
        capability=capability,
        enabled=None,
        actor=caller.user_id,
    )
    return _out(state)


@router.get("/audit", response_model=list[AuditEntry])
def audit(
    caller: Caller,
    policy: CurrentPolicy,
    conn: Db,
    group: GroupParam = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEntry]:
    """Who changed which switch, when, and under which environment config version."""
    groups = many_groups(conn, caller, "read_capabilities", policy, group)
    return [
        AuditEntry(
            group=r["group_id"],
            capability=r["capability"],
            action=r["action"],
            old_enabled=None if r["old_enabled"] is None else bool(r["old_enabled"]),
            new_enabled=bool(r["new_enabled"]),
            policy_file_id=r["policy_file_id"],
            at=r["created_at"],
            by=r["created_by"],
        )
        for r in repo.history(conn, groups, limit)
    ]
