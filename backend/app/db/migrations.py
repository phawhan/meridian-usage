"""Apply backend/database/*.sql in version order, each exactly once (see database/README.md)."""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database"
ACTOR = "system:startup"

_FILENAME = re.compile(r"^(?P<version>\d{14})_(?P<name>[a-z0-9_]+)\.sql$")

# Bookkeeping lives in code, not in a migration: it must exist before any migration runs.
_BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version    TEXT PRIMARY KEY,   -- YYYYMMDDHHMMSS prefix of the file name
    name       TEXT NOT NULL,      -- rest of the file name, e.g. create_meta
    sha256     TEXT NOT NULL,      -- content hash when applied; an edited file is refused
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """A migration file is misnamed, was edited after being applied, or failed to apply."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationError(f"{path.name}: expected YYYYMMDDHHMMSS_snake_name.sql")
        migrations.append(Migration(match["version"], match["name"], path.read_text()))
    return migrations


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the versions applied by this call."""
    conn.execute(_BOOKKEEPING)
    applied = {
        row["version"]: row["sha256"]
        for row in conn.execute("SELECT version, sha256 FROM schema_migration")
    }
    newly_applied = []
    for migration in discover(directory):
        if migration.version in applied:
            if applied[migration.version] != migration.sha256:
                raise MigrationError(
                    f"{migration.version}_{migration.name}.sql changed after it was applied;"
                    " add a new migration instead of editing this one"
                )
            continue
        _apply(conn, migration)
        newly_applied.append(migration.version)
    return newly_applied


def _apply(conn: sqlite3.Connection, migration: Migration) -> None:
    # executescript takes no parameters; the values below come from a filename that
    # matched _FILENAME and a hex digest, so they are safe to inline.
    script = (
        f"BEGIN;\n{migration.sql}\n"
        "INSERT INTO schema_migration (version, name, sha256, created_by) VALUES "
        f"('{migration.version}', '{migration.name}', '{migration.sha256}', '{ACTOR}');\n"
        "COMMIT;"
    )
    try:
        conn.executescript(script)
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.rollback()
        raise MigrationError(f"{migration.version}_{migration.name}.sql failed: {exc}") from exc
