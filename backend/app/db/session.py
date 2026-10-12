import sqlite3
from pathlib import Path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


class EnvironmentMismatchError(RuntimeError):
    """The database was created for a different environment than the one starting."""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, app_env: str) -> None:
    """Apply the schema and stamp the database with its environment on first use.

    Refuses to continue if the database already belongs to another environment, so prod
    rules never run against dev switch states or the other way round (D9).
    """
    conn.executescript(SCHEMA_FILE.read_text())
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('environment', ?)", (app_env,)
        )
    stored = conn.execute("SELECT value FROM meta WHERE key = 'environment'").fetchone()["value"]
    if stored != app_env:
        raise EnvironmentMismatchError(
            f"database belongs to '{stored}', refusing to start as '{app_env}'"
        )
