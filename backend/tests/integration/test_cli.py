import shutil
from pathlib import Path

import pytest

from app.cli import main
from app.core.config import REPO_ROOT


def test_sync_command_applies_then_reports_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(REPO_ROOT / "data" / "directory", tmp_path / "data" / "directory")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "staging.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    assert main(["sync"]) == 0
    assert main(["sync"]) == 0

    out = capsys.readouterr().out
    assert "[staging] sync run 1: directory applied" in out
    assert "users: read 22, inserted 22, updated 0, deactivated 0" in out
    assert "[staging] sync run 2: directory unchanged" in out
