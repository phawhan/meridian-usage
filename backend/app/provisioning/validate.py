"""Validate rendered config before anything is written or shipped. Each rule returns readable
problems; an empty list means valid. The rules:

  schema       every host file matches its JSON Schema; every manifest parses as a
               PermissionsManifest and turns back into the policy it was rendered from
  scopes       every contract tool needs the scope the connector's action needs
  groups       every group a baseline names exists in the directory
  names        plugin name == MCP server key == manifest server_name; unique across envs
  promotion    grants never widen from dev to staging to prod (roles and visibility)
  launch       the host's connector args parse, for the right environment
  user_config  every ${user_config.X} reference is declared in the plugin manifest
  hosts        each environment has its own loopback api_url; the release is pinned
  marketplace  every listed plugin source was rendered
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.connector.config import ConfigError, parse_config
from app.connector.tools import TOOL_ACTION
from app.core.config import Environment
from app.core.contract import TOOL_NAMES, tool_scope
from app.core.env_config import SCOPES, Policy
from app.provisioning.manifest import PermissionsManifest
from app.provisioning.render import ENVIRONMENTS, Files, release_source
from app.services.authz import REQUIRED_SCOPE

SCHEMA_DIR = Path(__file__).parent / "schemas"
SCHEMA_FOR = {
    "claude_desktop_config.json": "mcp-stdio-servers",
    ".mcp.json": "mcp-stdio-servers",
    "plugin.json": "claude-plugin",
    "marketplace.json": "claude-marketplace",
    "gemini_settings.json": "mcp-stdio-servers",
    "gemini-extension.json": "gemini-extension",
}
HOST_FILES = (
    "claude_desktop_config.json",
    ".mcp.json",
    "gemini_settings.json",
    "gemini-extension.json",
)
VISIBILITY_RANK = {"own_group": 0, "all": 1}
USER_CONFIG_REF = re.compile(r"\$\{user_config\.([A-Za-z_][A-Za-z0-9_]*)\}")


@cache
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text()))


def _parsed(files: Files) -> dict[str, Any]:
    return {path: json.loads(text) for path, text in files.items() if path.endswith(".json")}


def check_schemas(files: Files, policies: dict[Environment, Policy]) -> list[str]:
    problems = []
    for path, data in _parsed(files).items():
        schema = SCHEMA_FOR.get(Path(path).name)
        if schema:
            problems += [f"{path}: {e.message}" for e in _validator(schema).iter_errors(data)]
    for env, policy in policies.items():
        path = f"deploy/{env}/permissions.json"
        try:
            manifest = PermissionsManifest.model_validate_json(files[path])
        except (KeyError, ValidationError) as exc:
            problems.append(f"{path}: not a valid permissions manifest: {exc}")
            continue
        if manifest.policy() != policy:
            problems.append(f"{path}: does not reproduce {policy.path}")
    return problems


def check_scopes() -> list[str]:
    checked = {t: REQUIRED_SCOPE[TOOL_ACTION[t]] for t in TOOL_NAMES}
    return [
        f"contract tool {t} needs {tool_scope(t)}, the connector checks {checked[t]}"
        for t in TOOL_NAMES
        if tool_scope(t) != checked[t]
    ]


def check_groups(policies: dict[Environment, Policy], groups: list[str]) -> list[str]:
    return [
        f"{p.path} names group '{g}', which the directory doesn't have"
        for p in policies.values()
        for g in sorted(p.groups_named() - set(groups))
    ]


def check_names(files: Files, policies: dict[Environment, Policy]) -> list[str]:
    problems, data = [], _parsed(files)
    for env, policy in policies.items():
        base, name = f"deploy/{env}", policy.server_name
        found = {
            "plugin.json name": data[f"{base}/plugin/.claude-plugin/plugin.json"]["name"],
            ".mcp.json server": next(iter(data[f"{base}/plugin/.mcp.json"]["mcpServers"])),
            "desktop server": next(iter(data[f"{base}/claude_desktop_config.json"]["mcpServers"])),
            "gemini extension name": data[f"{base}/gemini-extension/gemini-extension.json"]["name"],
            "gemini server": next(iter(data[f"{base}/gemini_settings.json"]["mcpServers"])),
        }
        problems += [
            f"{env}: {k} is '{v}', expected '{name}'" for k, v in found.items() if v != name
        ]
    names = [p.server_name for p in policies.values()]
    if len(set(names)) != len(names):
        problems.append(f"server names must differ per environment: {names}")
    return problems


def check_promotion(policies: dict[Environment, Policy]) -> list[str]:
    """Moving towards prod may narrow access, never widen it."""
    problems = []
    for wider, narrower in zip(ENVIRONMENTS, ENVIRONMENTS[1:], strict=False):
        w, n = policies[wider].scopes, policies[narrower].scopes
        for scope in SCOPES:
            extra = set(n[scope].roles) - set(w[scope].roles)
            if extra:
                problems.append(f"{narrower} gives {sorted(extra)} {scope}, {wider} doesn't")
            if (
                VISIBILITY_RANK[n[scope].group_visibility]
                > VISIBILITY_RANK[w[scope].group_visibility]
            ):
                problems.append(f"{narrower} sees more groups for {scope} than {wider}")
    return problems


def _connector_args(server: dict[str, Any]) -> list[str]:
    args: list[str] = server["args"]
    return args[args.index("meridian-connector") + 1 :] if "meridian-connector" in args else []


def check_launch(files: Files) -> list[str]:
    problems = []
    for path, data in _parsed(files).items():
        if Path(path).name not in HOST_FILES:
            continue
        env = path.split("/")[1]
        for name, server in data["mcpServers"].items():
            argv = [USER_CONFIG_REF.sub("u", a) for a in _connector_args(server)]
            try:
                config = parse_config(argv, {"MERIDIAN_USER": "u"})  # Gemini: from settings
            except (ConfigError, SystemExit):
                problems.append(f"{path}: {name} would not start: {server['args']}")
                continue
            if config.env != env:
                problems.append(f"{path}: {name} starts in {config.env}, file is for {env}")
    return problems


def check_user_config(files: Files) -> list[str]:
    problems, data = [], _parsed(files)
    for env in ENVIRONMENTS:
        declared = set(
            data[f"deploy/{env}/plugin/.claude-plugin/plugin.json"].get("userConfig", {})
        )
        used = set(USER_CONFIG_REF.findall(files[f"deploy/{env}/plugin/.mcp.json"]))
        problems += [
            f"{env}: .mcp.json uses undeclared user_config.{k}" for k in sorted(used - declared)
        ]
    return problems


def check_hosts(files: Files, policies: dict[Environment, Policy], version: str) -> list[str]:
    problems = []
    urls = [p.api_url for p in policies.values()]
    if len(set(urls)) != len(urls):
        problems.append(f"each environment needs its own api_url: {urls}")
    problems += [
        f"{p.path}: api_url {p.api_url} is not a loopback http URL"
        for p in policies.values()
        if not re.fullmatch(r"http://(127\.0\.0\.1|localhost):\d+/?", p.api_url)
    ]
    for path, data in _parsed(files).items():
        for server in data.get("mcpServers", {}).values():
            if release_source(version) not in server["args"]:
                problems.append(f"{path}: connector is not pinned to {release_source(version)}")
    return problems


def check_marketplace(files: Files) -> list[str]:
    listing = _parsed(files)[".claude-plugin/marketplace.json"]
    return [
        f"marketplace lists {p['name']} at {p['source']}, which was not rendered"
        for p in listing["plugins"]
        if f"{p['source'].removeprefix('./')}/.claude-plugin/plugin.json" not in files
    ]


def validate(
    files: Files, policies: dict[Environment, Policy], groups: list[str], version: str
) -> list[str]:
    return (
        check_schemas(files, policies)
        + check_scopes()
        + check_groups(policies, groups)
        + check_names(files, policies)
        + check_promotion(policies)
        + check_launch(files)
        + check_user_config(files)
        + check_hosts(files, policies, version)
        + check_marketplace(files)
    )
