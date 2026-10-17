from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Dev settings with a throwaway database, so tests never touch var/."""
    return Settings(app_env="dev", db_path=tmp_path / "test.db")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # Entering the context runs the lifespan (schema, env marker), like a real start.
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
