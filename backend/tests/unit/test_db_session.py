from contextlib import closing
from pathlib import Path

import pytest

from app.db.session import EnvironmentMismatchError, connect, init_db


def test_new_database_is_stamped_with_its_environment(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "x.db")) as conn:
        init_db(conn, "dev")
        init_db(conn, "dev")
        rows = conn.execute("SELECT value, created_by FROM meta").fetchall()
        assert [tuple(r) for r in rows] == [("dev", "system:startup")]


def test_database_from_another_environment_is_refused_before_migrating(tmp_path: Path) -> None:
    db = tmp_path / "x.db"
    with closing(connect(db)) as conn:
        init_db(conn, "dev")
        applied = conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0]

    empty_migrations = tmp_path / "none"
    empty_migrations.mkdir()
    (empty_migrations / "20991231000000_prod_only.sql").write_text("CREATE TABLE x (id INT);")
    with closing(connect(db)) as conn:
        with pytest.raises(EnvironmentMismatchError, match="'dev'"):
            init_db(conn, "prod", migrations_dir=empty_migrations)
        # Nothing from the refused start reached the database.
        assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == applied


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "x.db")) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_missing_parent_directory_is_created(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "dir" / "x.db"
    with closing(connect(db)) as conn:
        init_db(conn, "staging")
    assert db.exists()
