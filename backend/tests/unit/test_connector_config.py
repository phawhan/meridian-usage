from pathlib import Path

import pytest

from app.connector.config import ConfigError, ConnectorConfig, parse_config

FULL = ["--user", "u_priya", "--env", "prod", "--manifest", "m.json"]


def test_reads_flags() -> None:
    assert parse_config(FULL, {}) == ConnectorConfig("u_priya", "prod", Path("m.json"), None)


def test_environment_variables_fill_in_and_flags_win() -> None:
    environ = {"MERIDIAN_USER": "u_env", "MERIDIAN_ENV": "dev", "MERIDIAN_MANIFEST": "x.json"}
    assert parse_config([], environ).user_id == "u_env"
    assert parse_config(["--user", "u_flag"], environ).user_id == "u_flag"


def test_names_every_missing_setting() -> None:
    with pytest.raises(ConfigError, match="missing --user, --env"):
        parse_config([], {})


def test_manifest_defaults_to_the_rendered_one() -> None:
    assert parse_config(["--user", "u", "--env", "dev"], {}).manifest is None


def test_rejects_unknown_environment() -> None:
    with pytest.raises(ConfigError, match="got 'production'"):
        parse_config(["--user", "u", "--env", "production", "--manifest", "m"], {})


@pytest.mark.parametrize("extra", [["--usr", "x"], ["--us", "x"]])
def test_rejects_unknown_or_abbreviated_flags(extra: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_config(["--env", "dev", "--manifest", "m", *extra], {})
