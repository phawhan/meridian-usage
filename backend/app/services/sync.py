"""One sync pass, recorded as a sync_run: everything the service takes in from outside.

Order matters:
  1. directory  - usage is attributed through it, and switches are seeded per group
  2. usage      - when the directory changed, every partition is re-derived
  3. policy     - the environment YAML in force is recorded (capability audit points at it)
  4. switches   - missing group x capability switches are seeded from the baseline
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.core.env_config import Policy, PolicyError
from app.repositories import directory, sync_log
from app.services import capabilities
from app.services.directory_sync import DirectorySyncResult, sync_directory
from app.services.ingestion.pipeline import IngestResult, ingest_usage

log = logging.getLogger(__name__)
POLICY_ACTOR = "system:startup"


class DirectoryUnavailableError(RuntimeError):
    """No valid directory snapshot has ever been applied, so no caller can be identified."""


@dataclass(frozen=True)
class SyncReport:
    run_id: int
    directory: DirectorySyncResult
    usage: IngestResult
    policy_file_id: int
    switches_seeded: int

    @property
    def problems(self) -> list[str]:
        found = [f"directory: {e}" for e in self.directory.errors]
        found += [f"{f.path}: {f.error}" for f in self.usage.rejected]
        return found

    @property
    def ok(self) -> bool:
        return not self.problems


def record_policy(conn: sqlite3.Connection, policy: Policy, run_id: int) -> int:
    """source_file id of the environment config in force, recording it if it changed."""
    if sync_log.latest_sha256(conn, policy.path) != policy.sha256:
        with conn:
            sync_log.record_file(
                conn,
                run_id=run_id,
                kind="environment_config",
                path=policy.path,
                sha256=policy.sha256,
                exported_at=None,
                actor=POLICY_ACTOR,
            )
    file_id = sync_log.latest_applied_id(conn, policy.path)
    assert file_id is not None
    return file_id


def check_policy_groups(conn: sqlite3.Connection, policy: Policy) -> None:
    """A typo in enabled_for would silently leave a group switched off; refuse instead."""
    known = {g.group_id for g in directory.list_groups(conn) if g.active}
    unknown = sorted(policy.groups_named() - known)
    if unknown:
        raise PolicyError(f"{policy.path} names groups not in the directory: {unknown}")


def run_sync(
    conn: sqlite3.Connection,
    settings: Settings,
    policy: Policy,
    trigger: Literal["startup", "cli"],
) -> SyncReport:
    run_id = sync_log.start_run(conn, trigger)
    try:
        dir_result = sync_directory(conn, settings.data_dir, run_id)
        if dir_result.status == "rejected" and not sync_log.has_applied(conn, "directory_users"):
            raise DirectoryUnavailableError(
                f"no valid directory snapshot available: {'; '.join(dir_result.errors)}"
            )
        usage = ingest_usage(
            conn, settings.data_dir, run_id, rebuild_all=dir_result.status == "applied"
        )
        check_policy_groups(conn, policy)
        policy_file_id = record_policy(conn, policy, run_id)
        seeded = capabilities.seed_missing(conn, policy, policy_file_id)
    except Exception as exc:
        sync_log.finish_run(conn, run_id, error=f"{type(exc).__name__}: {exc}")
        raise

    report = SyncReport(run_id, dir_result, usage, policy_file_id, seeded)
    sync_log.finish_run(conn, run_id, error="; ".join(report.problems) or None)
    for problem in report.problems:
        log.warning("sync run %s: rejected %s", run_id, problem)
    return report
