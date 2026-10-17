import sqlite3
from pathlib import Path

from app.db.migrations import MIGRATIONS_DIR, migrate


class EnvironmentMismatchError(RuntimeError):
    """The database was created for a different environment than the one starting."""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _stored_environment(conn: sqlite3.Connection) -> str | None:
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if not has_meta:
        return None
    row = conn.execute("SELECT value FROM meta WHERE key = 'environment'").fetchone()
    return row["value"] if row else None


def init_db(conn: sqlite3.Connection, app_env: str, migrations_dir: Path = MIGRATIONS_DIR) -> None:
    """Check the environment marker, apply pending migrations, stamp a new database.

    The marker is checked before migrating, so starting as dev against prod's database
    changes nothing in it (D9).
    """
    stored = _stored_environment(conn)
    if stored is not None and stored != app_env:
        raise EnvironmentMismatchError(
            f"database belongs to '{stored}', refusing to start as '{app_env}'"
        )
    migrate(conn, migrations_dir)
    if stored is None:
        with conn:
            conn.execute(
                "INSERT INTO meta (key, value, created_by, updated_by)"
                " VALUES ('environment', ?, 'system:startup', 'system:startup')",
                (app_env,),
            )
