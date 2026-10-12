"""One sync pass: take in whatever is new under DATA_DIR, recorded as a sync_run.

S1 handles the directory snapshot; S2 adds usage exports to the same pass.
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.repositories import sync_log
from app.services.directory_sync import DirectorySyncResult, sync_directory

log = logging.getLogger(__name__)


class DirectoryUnavailableError(RuntimeError):
    """No valid directory snapshot has ever been applied, so no caller can be identified."""


@dataclass(frozen=True)
class SyncReport:
    run_id: int
    directory: DirectorySyncResult

    @property
    def ok(self) -> bool:
        return self.directory.status != "rejected"


def run_sync(
    conn: sqlite3.Connection, settings: Settings, trigger: Literal["startup", "cli"]
) -> SyncReport:
    run_id = sync_log.start_run(conn, trigger)
    try:
        result = sync_directory(conn, settings.data_dir, run_id)
    except Exception as exc:
        sync_log.finish_run(conn, run_id, error=f"{type(exc).__name__}: {exc}")
        raise

    error = "; ".join(result.errors) if result.status == "rejected" else None
    sync_log.finish_run(conn, run_id, error=error)
    if error:
        if not sync_log.has_applied(conn, "directory_users"):
            raise DirectoryUnavailableError(f"no valid directory snapshot available: {error}")
        log.warning("directory snapshot rejected, keeping the previous mirror: %s", error)
    return SyncReport(run_id=run_id, directory=result)
