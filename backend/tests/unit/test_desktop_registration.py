import json
from pathlib import Path

import pytest

from app.provisioning.desktop import RegistrationError, desktop_entry, merge, register

PRIYA = "user_E7691888F28227066DD2FB86"


def test_release_entry_fills_the_user_and_pins_the_release() -> None:
    name, entry = desktop_entry("prod", PRIYA, "release")
    assert name == "meridian-usage"
    assert Path(entry["command"]).is_absolute() and entry["command"].endswith("uvx")
    assert entry["args"][-4:] == ["--env", "prod", "--user", PRIYA]
    assert any(
        a.startswith("git+https://github.com/phawhan/meridian-usage@v") for a in entry["args"]
    )


def test_local_entry_runs_this_checkout() -> None:
    _, entry = desktop_entry("dev", PRIYA, "local")
    assert entry["args"][:2] == ["run", "--project"]
    assert entry["args"][3:] == ["meridian-connector", "--env", "dev", "--user", PRIYA]


def test_unknown_user_is_refused() -> None:
    with pytest.raises(RegistrationError, match="not a user"):
        desktop_entry("prod", "user_NOPE", "release")


def test_merge_keeps_other_servers_and_settings() -> None:
    existing = {"mcpServers": {"filesystem": {"command": "npx"}}, "globalShortcut": "Cmd+K"}
    merged = merge(existing, "meridian-usage", {"command": "uvx", "args": []})
    assert merged["globalShortcut"] == "Cmd+K"
    assert set(merged["mcpServers"]) == {"filesystem", "meridian-usage"}
    assert existing["mcpServers"] == {"filesystem": {"command": "npx"}}  # not mutated


def test_register_backs_up_the_existing_config(tmp_path: Path) -> None:
    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}}))
    register("staging", PRIYA, "release", config)
    assert "meridian-usage-staging" in json.loads(config.read_text())["mcpServers"]
    assert len(list(tmp_path.glob("claude_desktop_config.json.bak-*"))) == 1
