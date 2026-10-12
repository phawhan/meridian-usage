from contextlib import closing
from pathlib import Path

import pytest

from app.db.session import EnvironmentMismatchError, connect, init_db


def test_schema_applies_twice_without_error(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "x.db")) as conn:
        init_db(conn, "dev")
        init_db(conn, "dev")
        row = conn.execute("SELECT value FROM meta WHERE key = 'environment'").fetchone()
        assert row[0] == "dev"


def test_database_from_another_environment_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "x.db"
    with closing(connect(db)) as conn:
        init_db(conn, "dev")
    with closing(connect(db)) as conn, pytest.raises(EnvironmentMismatchError, match="'dev'"):
        init_db(conn, "prod")


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "x.db")) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_missing_parent_directory_is_created(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "dir" / "x.db"
    with closing(connect(db)) as conn:
        init_db(conn, "staging")
    assert db.exists()
