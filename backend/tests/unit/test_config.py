from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import REPO_ROOT, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the developer's shell (e.g. an exported APP_ENV) out of these tests.
    for name in ("APP_ENV", "DB_PATH", "DATA_DIR", "ENV_DIR"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_dev_with_per_env_database() -> None:
    settings = Settings()
    assert settings.app_env == "dev"
    assert settings.database_file == REPO_ROOT / "var" / "dev.db"
    assert settings.env_config_file == REPO_ROOT / "environments" / "dev.yaml"


def test_reads_app_env_and_db_path_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DB_PATH", "/tmp/custom.db")
    settings = Settings()
    assert settings.app_env == "prod"
    assert settings.database_file == Path("/tmp/custom.db")
    assert settings.env_config_file.name == "prod.yaml"


def test_unknown_environment_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "qa")
    with pytest.raises(ValidationError):
        Settings()
