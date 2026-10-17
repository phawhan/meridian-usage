"""Provisioning: one render for all three environments, valid, deterministic, and identical to
what is committed. Each validation rule has a fixture that breaks it."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.connector import tools
from app.core.config import REPO_ROOT
from app.core.env_config import ScopeRule
from app.provisioning import validate as v
from app.provisioning.command import differences, provision
from app.provisioning.render import Files, Rendering, render_all


@pytest.fixture(scope="module")
def rendering() -> Rendering:
    return render_all()


def edited(files: Files, path: str, change: Callable[[Any], None]) -> Files:
    data = json.loads(files[path])
    change(data)
    return files | {path: json.dumps(data)}


def problems(r: Rendering, files: Files | None = None, **overrides: Any) -> list[str]:
    args = {"policies": r.policies, "groups": r.groups, "version": r.version} | overrides
    return v.validate(files or r.files, **args)


def test_renders_three_environments_validly(rendering: Rendering) -> None:
    assert problems(rendering) == []
    assert sorted(rendering.policies) == ["dev", "prod", "staging"]
    assert len(rendering.files) == 23


def test_render_is_deterministic(rendering: Rendering) -> None:
    assert render_all().files == rendering.files


def test_committed_config_is_what_the_inputs_render(rendering: Rendering) -> None:
    assert differences(rendering, REPO_ROOT) == [], "run `make provision`"


def test_prod_manifest_reads_as_the_starter_kit_says(rendering: Rendering) -> None:
    prod = json.loads(rendering.files["deploy/prod/permissions.json"])
    assert prod["tools"]["set_capability"] == {
        "scope": "capabilities:write",
        "roles": ["platform_admin"],
    }
    assert prod["baseline"]["finance"]["usage-connector"] is False
    assert prod["baseline"]["clinical-operations"]["usage-connector"] is True
    assert all(not g["code-execution"] for g in prod["baseline"].values())


# --- one failing fixture per rule ---

MCP = "deploy/prod/plugin/.mcp.json"
PLUGIN = "deploy/prod/plugin/.claude-plugin/plugin.json"


def test_schema_rule(rendering: Rendering) -> None:
    files = edited(rendering.files, PLUGIN, lambda d: d.update(name="Meridian Usage"))
    assert any("does not match" in p for p in problems(rendering, files))


def test_manifest_must_reproduce_its_policy(rendering: Rendering) -> None:
    path = "deploy/prod/permissions.json"
    files = edited(
        rendering.files, path, lambda d: d["scopes"]["usage:read"]["roles"].append("member")
    )
    assert f"{path}: does not reproduce environments/prod.yaml" in problems(rendering, files)


def test_scope_rule(rendering: Rendering, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(tools.TOOL_ACTION, "set_capability", "read_usage")
    assert any("set_capability needs capabilities:write" in p for p in problems(rendering))


def test_group_rule(rendering: Rendering) -> None:
    groups = [g for g in rendering.groups if g != "clinical-operations"]
    assert any("'clinical-operations'" in p for p in problems(rendering, groups=groups))


def test_name_rule(rendering: Rendering) -> None:
    files = edited(
        rendering.files, MCP, lambda d: d.update(mcpServers={"usage": d["mcpServers"].popitem()[1]})
    )
    assert "prod: .mcp.json server is 'usage', expected 'meridian-usage'" in problems(
        rendering, files
    )


def test_promotion_rule(rendering: Rendering) -> None:
    prod = rendering.policies["prod"]
    wider = prod.scopes | {"usage:read": ScopeRule(roles=["member", "team_lead"])}
    policies = rendering.policies | {"prod": replace(prod, scopes=wider)}
    assert "prod gives ['member'] usage:read, staging doesn't" in v.check_promotion(policies)


def test_launch_rule(rendering: Rendering) -> None:
    def set_env(value: str) -> Callable[[Any], None]:
        def change(d: Any) -> None:
            args = d["mcpServers"]["meridian-usage"]["args"]
            args[args.index("--env") + 1] = value

        return change

    wrong_env = edited(rendering.files, MCP, set_env("dev"))
    bad_env = edited(rendering.files, MCP, set_env("production"))
    assert any("starts in dev, file is for prod" in p for p in problems(rendering, wrong_env))
    assert any("would not start" in p for p in problems(rendering, bad_env))


def test_user_config_rule(rendering: Rendering) -> None:
    files = edited(
        rendering.files,
        MCP,
        lambda d: d["mcpServers"]["meridian-usage"]["args"].append("${user_config.team}"),
    )
    assert "prod: .mcp.json uses undeclared user_config.team" in problems(rendering, files)


def test_host_rules(rendering: Rendering) -> None:
    prod = rendering.policies["prod"]
    shared = rendering.policies | {"prod": replace(prod, api_url="http://127.0.0.1:8000")}
    remote = rendering.policies | {"prod": replace(prod, api_url="http://usage.example.com")}
    assert any("own api_url" in p for p in v.check_hosts(rendering.files, shared, "0.2.0"))
    assert any("not a loopback" in p for p in v.check_hosts(rendering.files, remote, "0.2.0"))
    assert any("not pinned" in p for p in problems(rendering, version="9.9.9"))


def test_marketplace_rule(rendering: Rendering) -> None:
    files = edited(
        rendering.files,
        ".claude-plugin/marketplace.json",
        lambda d: d["plugins"].append(
            {"name": "qa", "source": "./deploy/qa/plugin", "description": "x"}
        ),
    )
    assert any(
        "./deploy/qa/plugin, which was not rendered" in p for p in problems(rendering, files)
    )


# --- the command ---


def test_check_catches_hand_edits_and_stray_files(rendering: Rendering, tmp_path: Path) -> None:
    for path, content in rendering.files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content)
    assert differences(rendering, tmp_path) == []
    (tmp_path / MCP).write_text("{}")
    (tmp_path / "deploy/prod/notes.json").write_text("{}")
    assert differences(rendering, tmp_path) == [
        f"differs: {MCP}",
        "not rendered (hand-made?): deploy/prod/notes.json",
    ]


def test_provision_writes_then_check_passes(tmp_path: Path) -> None:
    assert provision(check=True, root=tmp_path) == 1
    (tmp_path / "deploy/old.json").parent.mkdir(parents=True)
    (tmp_path / "deploy/old.json").write_text("{}")
    assert provision(check=False, root=tmp_path) == 0
    assert not (tmp_path / "deploy/old.json").exists()
    assert provision(check=True, root=tmp_path) == 0
