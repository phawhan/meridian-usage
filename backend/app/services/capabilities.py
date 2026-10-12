"""Per-group capability switches: baseline seeding, reads with drift, audited changes.

Authorisation is not checked here; callers go through services.authz.enforce first.
"""

import sqlite3
from dataclasses import dataclass

from app.core.clock import utc_now_iso
from app.core.env_config import Policy
from app.models.domain import CAPABILITIES, Capability
from app.repositories import capabilities as repo
from app.repositories import directory
from app.repositories.capabilities import AuditAction

SEED_ACTOR = "system:startup"


@dataclass(frozen=True)
class CapabilityState:
    group_id: str
    capability: Capability
    enabled: bool
    baseline: bool  # what the environment's capability_defaults say
    updated_at: str
    updated_by: str

    @property
    def drift(self) -> bool:
        """Changed by a person away from the environment baseline."""
        return self.enabled != self.baseline


def seed_missing(conn: sqlite3.Connection, policy: Policy, policy_file_id: int) -> int:
    """Create switches that don't exist yet, from the baseline; never overwrite (D5).
    Covers first start and groups that appear in the directory later."""
    now = utc_now_iso()
    have = repo.existing(conn)
    created = 0
    with conn:
        for group in directory.list_groups(conn):
            if not group.active:
                continue
            for capability in CAPABILITIES:
                if (group.group_id, capability) in have:
                    continue
                enabled = policy.default_for(group.group_id, capability)
                repo.insert(conn, group.group_id, capability, enabled, SEED_ACTOR, now)
                repo.audit(
                    conn,
                    group_id=group.group_id,
                    capability=capability,
                    action="seed",
                    old=None,
                    new=enabled,
                    policy_file_id=policy_file_id,
                    actor=SEED_ACTOR,
                    now=now,
                )
                created += 1
    return created


def states(conn: sqlite3.Connection, policy: Policy, group_ids: list[str]) -> list[CapabilityState]:
    if not group_ids:
        return []
    return [
        CapabilityState(
            group_id=row["group_id"],
            capability=row["capability"],
            enabled=bool(row["enabled"]),
            baseline=policy.default_for(row["group_id"], row["capability"]),
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
        )
        for row in repo.rows(conn, group_ids)
    ]


def change(
    conn: sqlite3.Connection,
    policy: Policy,
    policy_file_id: int,
    *,
    group_id: str,
    capability: Capability,
    enabled: bool | None,
    actor: str,
) -> CapabilityState:
    """Set a switch, or reset it to the baseline when enabled is None.

    Setting a switch to the value it already has changes nothing and writes no audit row,
    so repeating a request is safe."""
    action: AuditAction = "reset" if enabled is None else "set"
    target = policy.default_for(group_id, capability) if enabled is None else enabled
    now = utc_now_iso()
    with conn:
        current = repo.get(conn, group_id, capability)
        if current is None:
            raise LookupError(f"no capability switch {capability!r} for group {group_id!r}")
        old = bool(current["enabled"])
        if old != target:
            repo.update(conn, group_id, capability, target, actor, now)
            repo.audit(
                conn,
                group_id=group_id,
                capability=capability,
                action=action,
                old=old,
                new=target,
                policy_file_id=policy_file_id,
                actor=actor,
                now=now,
            )
    [state] = [s for s in states(conn, policy, [group_id]) if s.capability == capability]
    return state
