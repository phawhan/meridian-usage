"""One sync pass: take in whatever is new under DATA_DIR, recorded as a sync_run.

Order matters: the directory first, because usage is attributed through it. When the
directory changes, every usage partition is re-derived so attribution follows.
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.repositories import sync_log
from app.services.directory_sync import DirectorySyncResult, sync_directory
from app.services.ingestion.pipeline import IngestResult, ingest_usage

log = logging.getLogger(__name__)


class DirectoryUnavailableError(RuntimeError):
    """No valid directory snapshot has ever been applied, so no caller can be identified."""


@dataclass(frozen=True)
class SyncReport:
    run_id: int
    directory: DirectorySyncResult
    usage: IngestResult

    @property
    def problems(self) -> list[str]:
        found = [f"directory: {e}" for e in self.directory.errors]
        found += [f"{f.path}: {f.error}" for f in self.usage.rejected]
        return found

    @property
    def ok(self) -> bool:
        return not self.problems


def run_sync(
    conn: sqlite3.Connection, settings: Settings, trigger: Literal["startup", "cli"]
) -> SyncReport:
    run_id = sync_log.start_run(conn, trigger)
    try:
        directory = sync_directory(conn, settings.data_dir, run_id)
        if directory.status == "rejected" and not sync_log.has_applied(conn, "directory_users"):
            raise DirectoryUnavailableError(
                f"no valid directory snapshot available: {'; '.join(directory.errors)}"
            )
        usage = ingest_usage(
            conn, settings.data_dir, run_id, rebuild_all=directory.status == "applied"
        )
    except Exception as exc:
        sync_log.finish_run(conn, run_id, error=f"{type(exc).__name__}: {exc}")
        raise

    report = SyncReport(run_id=run_id, directory=directory, usage=usage)
    sync_log.finish_run(conn, run_id, error="; ".join(report.problems) or None)
    for problem in report.problems:
        log.warning("sync run %s: rejected %s", run_id, problem)
    return report
