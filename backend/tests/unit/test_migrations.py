import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.migrations import MIGRATIONS_DIR, MigrationError, discover, migrate
from app.db.session import connect


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "x.db")
    yield connection
    connection.close()


@pytest.fixture
def migrations(tmp_path: Path) -> Path:
    """A private copy of the real migrations that a test may edit."""
    return Path(shutil.copytree(MIGRATIONS_DIR, tmp_path / "database"))


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_real_migrations_are_named_and_ordered() -> None:
    versions = [m.version for m in discover()]
    assert versions == sorted(versions) and len(versions) == len(set(versions))


def test_applies_all_then_nothing(conn: sqlite3.Connection) -> None:
    first = migrate(conn)
    second = migrate(conn)

    assert first == [m.version for m in discover()]
    assert second == []
    assert {"meta", "sync_run", "source_file", "users", "usage_fact", "ingest_issue"} <= tables(
        conn
    )
    row = conn.execute("SELECT * FROM schema_migration ORDER BY version").fetchone()
    assert (row["name"], row["created_by"]) == ("create_meta", "system:startup")


def test_new_migration_is_applied_on_next_start(conn: sqlite3.Connection, migrations: Path) -> None:
    migrate(conn, migrations)
    (migrations / "20991231000000_create_extra.sql").write_text("CREATE TABLE extra (id INTEGER);")

    assert migrate(conn, migrations) == ["20991231000000"]
    assert "extra" in tables(conn)


def test_editing_an_applied_migration_is_refused(
    conn: sqlite3.Connection, migrations: Path
) -> None:
    migrate(conn, migrations)
    meta = next(migrations.glob("*_create_meta.sql"))
    meta.write_text(meta.read_text() + "\n-- harmless looking edit\n")

    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(conn, migrations)


def test_failed_migration_leaves_nothing_behind(conn: sqlite3.Connection, migrations: Path) -> None:
    migrate(conn, migrations)
    (migrations / "20991231000000_broken.sql").write_text(
        "CREATE TABLE half_done (id INTEGER);\nCREATE TABLE meta (id INTEGER);"  # meta exists
    )

    with pytest.raises(MigrationError, match="broken.sql failed"):
        migrate(conn, migrations)
    assert "half_done" not in tables(conn)
    assert conn.execute("SELECT 1 FROM schema_migration WHERE name = 'broken'").fetchone() is None


def test_misnamed_file_is_refused(conn: sqlite3.Connection, migrations: Path) -> None:
    (migrations / "add_column.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationError, match="expected YYYYMMDDHHMMSS_snake_name.sql"):
        migrate(conn, migrations)
