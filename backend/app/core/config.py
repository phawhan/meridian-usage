from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is four levels up
REPO_ROOT = Path(__file__).resolve().parents[3]

Environment = Literal["dev", "staging", "prod"]


class Settings(BaseSettings):
    """Process settings, read from environment variables (APP_ENV, DB_PATH, DATA_DIR, ENV_DIR)."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: Environment = "dev"
    db_path: Path | None = None
    data_dir: Path = REPO_ROOT / "data"
    env_dir: Path = REPO_ROOT / "environments"

    @property
    def database_file(self) -> Path:
        # One database per environment unless DB_PATH says otherwise (D9).
        return self.db_path or REPO_ROOT / "var" / f"{self.app_env}.db"

    @property
    def env_config_file(self) -> Path:
        return self.env_dir / f"{self.app_env}.yaml"
