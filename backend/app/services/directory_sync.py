"""Mirror the identity provider snapshot (data/directory/) into the database.

users.json and groups.json are one snapshot: they are validated together and applied in a
single transaction, or rejected together and the previous mirror stays in force.
"""

import hashlib
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.core.clock import utc_now_iso
from app.models.sources.directory import GroupsFile, UsersFile
from app.repositories import directory, sync_log
from app.repositories.sync_log import FileCounts


@dataclass(frozen=True)
class DirectorySyncResult:
    status: Literal["applied", "unchanged", "rejected"]
    errors: tuple[str, ...] = ()
    users: FileCounts | None = None
    groups: FileCounts | None = None


@dataclass(frozen=True)
class _File:
    path: str  # relative to the data dir's parent, e.g. data/directory/users.json
    sha256: str
    content: bytes


def _read(path: Path, data_dir: Path) -> _File:
    content = path.read_bytes()
    return _File(
        path=path.relative_to(data_dir.parent).as_posix(),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


def _duplicates(label: str, values: list[str]) -> list[str]:
    return [f"duplicate {label} {value!r}" for value, n in Counter(values).items() if n > 1]


def validate_snapshot(users_file: UsersFile, groups_file: GroupsFile) -> list[str]:
    """Every rule the mirror relies on. Returns all problems, not just the first."""
    users, groups = users_file.users, groups_file.groups
    errors: list[str] = []
    if not users:
        errors.append("users.json lists no users; refusing to deactivate everyone")
    if not groups:
        errors.append("groups.json lists no groups; refusing to deactivate every group")

    errors += _duplicates("user_id", [u.user_id for u in users])
    errors += _duplicates("email", [u.email for u in users])
    errors += _duplicates("group_id", [g.group_id for g in groups])
    errors += _duplicates("claude_rbac_group_id", [g.claude_rbac_group_id for g in groups])
    errors += _duplicates("gcp_project_id", [g.gcp_project_id for g in groups])

    group_ids = {g.group_id for g in groups}
    for user in users:
        if not user.group_ids:
            errors.append(f"user {user.user_id} belongs to no group")
        errors += [
            f"user {user.user_id} references unknown group {g!r}"
            for g in user.group_ids
            if g not in group_ids
        ]

    users_by_id = {u.user_id: u for u in users}
    for group in groups:
        lead = users_by_id.get(group.team_lead_user_id)
        if lead is None:
            errors.append(f"group {group.group_id}: lead {group.team_lead_user_id} is not a user")
        elif group.group_id not in lead.group_ids:
            errors.append(f"group {group.group_id}: lead {lead.user_id} is not a member")
        elif lead.role != "team_lead":
            errors.append(f"group {group.group_id}: lead {lead.user_id} has role {lead.role}")
    return errors


def _describe(exc: ValidationError) -> list[str]:
    return [f"{exc.title}: {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]


def _record_pair(
    conn: sqlite3.Connection,
    run_id: int,
    files: tuple[_File, _File],
    exported_at: tuple[str | None, str | None],
    errors: list[str],
) -> tuple[int, int]:
    """Record users.json and groups.json as one snapshot: both applied or both rejected."""
    kinds: tuple[sync_log.SourceKind, sync_log.SourceKind] = ("directory_users", "directory_groups")
    users_id, groups_id = (
        sync_log.record_file(
            conn,
            run_id=run_id,
            kind=kind,
            path=file.path,
            sha256=file.sha256,
            exported_at=exported,
            actor=directory.SYNC_ACTOR,
            error="; ".join(errors) if errors else None,
        )
        for kind, file, exported in zip(kinds, files, exported_at, strict=True)
    )
    return users_id, groups_id


def sync_directory(conn: sqlite3.Connection, data_dir: Path, run_id: int) -> DirectorySyncResult:
    folder = data_dir / "directory"
    missing = [name for name in ("users.json", "groups.json") if not (folder / name).is_file()]
    if missing:
        return DirectorySyncResult("rejected", tuple(f"missing {folder / m}" for m in missing))

    files = (_read(folder / "users.json", data_dir), _read(folder / "groups.json", data_dir))
    if all(sync_log.latest_sha256(conn, f.path) == f.sha256 for f in files):
        return DirectorySyncResult("unchanged")

    try:
        users_file = UsersFile.model_validate_json(files[0].content)
        groups_file = GroupsFile.model_validate_json(files[1].content)
    except ValidationError as exc:
        errors = _describe(exc)
        with conn:
            _record_pair(conn, run_id, files, (None, None), errors)
        return DirectorySyncResult("rejected", tuple(errors))

    exported_at = (users_file.exported_at, groups_file.exported_at)
    errors = validate_snapshot(users_file, groups_file)
    if errors:
        with conn:
            _record_pair(conn, run_id, files, exported_at, errors)
        return DirectorySyncResult("rejected", tuple(errors))

    now = utc_now_iso()
    with conn:
        users_id, groups_id = _record_pair(conn, run_id, files, exported_at, [])
        group_counts = directory.upsert_snapshot(
            conn,
            "groups",
            "group_id",
            [g.model_dump() for g in groups_file.groups],
            file_id=groups_id,
            now=now,
        )
        user_counts = directory.upsert_snapshot(
            conn,
            "users",
            "user_id",
            [
                u.model_dump(exclude={"group_ids"}) | {"claude_seat": int(u.claude_seat)}
                for u in users_file.users
            ],
            file_id=users_id,
            now=now,
        )
        directory.sync_memberships(
            conn, {(u.user_id, g) for u in users_file.users for g in u.group_ids}, now
        )
        sync_log.set_counts(conn, users_id, user_counts)
        sync_log.set_counts(conn, groups_id, group_counts)
    return DirectorySyncResult("applied", users=user_counts, groups=group_counts)
