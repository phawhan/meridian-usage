import shutil
from pathlib import Path

import pytest
import yaml

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import PolicyError, load_policy


@pytest.fixture
def env_dir(tmp_path: Path) -> Path:
    return Path(shutil.copytree(REPO_ROOT / "environments", tmp_path / "environments"))


def edit(env_dir: Path, env: str, text_from: str, text_to: str) -> None:
    path = env_dir / f"{env}.yaml"
    content = path.read_text()
    assert text_from in content
    path.write_text(content.replace(text_from, text_to))


def test_all_three_environments_load_with_the_starter_kit_baseline() -> None:
    dev, staging, prod = (load_policy(Settings(app_env=e)) for e in ("dev", "staging", "prod"))
    assert dev.default_for("finance", "code-execution") is True
    assert staging.default_for("finance", "code-execution") is False
    assert prod.default_for("finance", "usage-connector") is False
    assert prod.default_for("clinical-operations", "usage-connector") is True
    assert prod.default_for("it-platform", "usage-connector") is True
    assert prod.groups_named() == {"it-platform", "clinical-operations"}
    assert (prod.path, prod.server_name) == ("environments/prod.yaml", "meridian-usage")


def test_typo_in_a_key_stops_startup(env_dir: Path) -> None:
    edit(env_dir, "prod", "group_visibility", "group_visiblity")
    with pytest.raises(PolicyError, match="prod.yaml is invalid"):
        load_policy(Settings(app_env="prod", env_dir=env_dir))


def test_unknown_role_stops_startup(env_dir: Path) -> None:
    edit(env_dir, "prod", "roles: [platform_admin]", "roles: [platform_admin, superuser]")
    with pytest.raises(PolicyError):
        load_policy(Settings(app_env="prod", env_dir=env_dir))


def test_missing_capability_default_stops_startup(env_dir: Path) -> None:
    edit(env_dir, "prod", "  code-execution: disabled\n", "")
    with pytest.raises(PolicyError, match="code-execution"):
        load_policy(Settings(app_env="prod", env_dir=env_dir))


def test_file_for_another_environment_is_refused(env_dir: Path) -> None:
    edit(env_dir, "prod", "environment: prod", "environment: dev")
    with pytest.raises(PolicyError, match="declares environment 'dev'"):
        load_policy(Settings(app_env="prod", env_dir=env_dir))


def test_missing_visibility_fails_closed_to_own_group(env_dir: Path) -> None:
    path = env_dir / "dev.yaml"
    config = yaml.safe_load(path.read_text())
    del config["scopes"]["usage:read"]["group_visibility"]
    path.write_text(yaml.safe_dump(config))
    policy = load_policy(Settings(app_env="dev", env_dir=env_dir))
    assert policy.scopes["usage:read"].group_visibility == "own_group"


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="not found"):
        load_policy(Settings(app_env="prod", env_dir=tmp_path))
