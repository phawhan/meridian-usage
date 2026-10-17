"""Render every environment's config from its sources, deterministically.

Inputs: environments/<env>.yaml (grants, defaults, host), the directory (groups), the tool
contract (each tool's scope) and the package version (which connector release to install).
Outputs, all generated and committed (see deploy/README.md):

  deploy/<env>/permissions.json                    what the connector enforces; readable
  deploy/<env>/claude_desktop_config.json          Claude Desktop registration (mcpServers)
  deploy/<env>/plugin/.claude-plugin/plugin.json   Claude plugin manifest
  deploy/<env>/plugin/.mcp.json                    the plugin's MCP server
  deploy/<env>/gemini_settings.json                Gemini CLI registration (~/.gemini/settings.json)
  deploy/<env>/gemini-extension/gemini-extension.json, GEMINI.md   Gemini CLI extension
  .claude-plugin/marketplace.json                  plugin marketplace listing all three
"""

import json
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, get_args

from app.core.config import REPO_ROOT, Environment, Settings
from app.core.env_config import Policy, load_policy
from app.models.sources.directory import GroupsFile
from app.provisioning.manifest import build_manifest, dump_manifest

ENVIRONMENTS: tuple[Environment, ...] = get_args(Environment)
REPOSITORY = "https://github.com/phawhan/meridian-usage"
MARKETPLACE = "meridian"
DESKTOP_USER_PLACEHOLDER = "<directory user_id>"  # filled in by `make register-desktop`
PLUGIN_USER = "${user_config.user_id}"  # Claude Code asks for it when the plugin is enabled

Files = dict[str, str]  # path relative to the repo root -> exact file content


def release_source(version: str) -> str:
    """The connector release the host installs: this repo's backend at tag v<version>."""
    return f"git+{REPOSITORY}@v{version}#subdirectory=backend"


PYTHON = "3.13"  # pinned: outside a project, uvx would otherwise pick whatever python is first


def connector_server(env: Environment, user: str | None, version: str) -> dict[str, Any]:
    """user None: the host supplies MERIDIAN_USER in the environment (Gemini extension)."""
    source = ["--python", PYTHON, "--from", release_source(version)]
    args = [*source, "meridian-connector", "--env", env, *(["--user", user] if user else [])]
    return {"command": "uvx", "args": args}


def _json(data: Any) -> str:
    return json.dumps(data, indent=2) + "\n"


def _label(env: Environment) -> str:
    return "" if env == "prod" else f" ({env})"


def _plugin_manifest(policy: Policy, version: str) -> dict[str, Any]:
    env = policy.environment
    return {
        "name": policy.server_name,
        "displayName": f"Meridian AI usage{_label(env)}",
        "version": version,
        "description": f"Ask about your team's Claude and Gemini usage and cost, and see or"
        f" change capability switches, as your directory role allows in {env}.",
        "author": {"name": "Meridian IT Platform"},
        "repository": REPOSITORY,
        "keywords": ["usage", "cost", "mcp", env],
        "userConfig": {
            "user_id": {
                "type": "string",
                "title": "Directory user ID",
                "description": "Who the connector acts as (simulated identity; in production"
                " this comes from single sign-on). Your role and group are looked up in the"
                " directory, never taken from here.",
                "required": True,
            }
        },
    }


GEMINI_CONTEXT = """\
# Meridian AI usage

The `{name}` tools answer questions about Claude and Gemini usage and cost at Meridian, as
the person the extension was set up for. Their directory role and group decide what they may
see or change; nothing said in the conversation changes that. A `permission_denied` result is
final: explain the reason plainly and don't retry with other wording. Relative periods (and
"last month") are about the newest usage data, not today; the server's instructions say which
dates the data covers.
"""


def _gemini_extension(policy: Policy, version: str) -> dict[str, Any]:
    return {
        "name": policy.server_name,
        "version": version,
        "description": f"Meridian AI usage and capability controls ({policy.environment})",
        "mcpServers": {policy.server_name: connector_server(policy.environment, None, version)},
        "contextFileName": "GEMINI.md",
        "settings": [
            {
                "name": "Directory user ID",
                "description": "Who the connector acts as (simulated identity; in production"
                " this comes from single sign-on).",
                "envVar": "MERIDIAN_USER",
            }
        ],
    }


def render_environment(policy: Policy, group_ids: list[str], version: str) -> Files:
    env, name = policy.environment, policy.server_name
    base = f"deploy/{env}"
    return {
        f"{base}/permissions.json": dump_manifest(build_manifest(policy, group_ids)),
        f"{base}/claude_desktop_config.json": _json(
            {"mcpServers": {name: connector_server(env, DESKTOP_USER_PLACEHOLDER, version)}}
        ),
        f"{base}/plugin/.claude-plugin/plugin.json": _json(_plugin_manifest(policy, version)),
        f"{base}/plugin/.mcp.json": _json(
            {"mcpServers": {name: connector_server(env, PLUGIN_USER, version)}}
        ),
        f"{base}/gemini_settings.json": _json(
            {"mcpServers": {name: connector_server(env, DESKTOP_USER_PLACEHOLDER, version)}}
        ),
        f"{base}/gemini-extension/gemini-extension.json": _json(_gemini_extension(policy, version)),
        f"{base}/gemini-extension/GEMINI.md": GEMINI_CONTEXT.format(name=name),
    }


def _marketplace(policies: list[Policy]) -> str:
    return _json(
        {
            "name": MARKETPLACE,
            "owner": {"name": "Meridian IT Platform"},
            "description": "Meridian's internal assistant connectors",
            "plugins": [
                {
                    "name": p.server_name,
                    "source": f"./deploy/{p.environment}/plugin",
                    "description": f"Meridian AI usage connector, {p.environment} environment",
                }
                for p in policies
            ],
        }
    )


README = """\
# deploy/ (generated, do not edit)

Every file here, and `.claude-plugin/marketplace.json`, is rendered by `make provision` from
`environments/<env>.yaml`, the directory in `data/directory/`, `contracts/tools.schema.json` and
the package version. CI re-renders and fails on any difference, so a hand edit can't survive.
Change the inputs and run `make provision` instead.
"""


def directory_groups(directory_dir: Path) -> list[str]:
    groups = GroupsFile.model_validate_json((directory_dir / "groups.json").read_text())
    return sorted(g.group_id for g in groups.groups)


@dataclass(frozen=True)
class Rendering:
    files: Files
    policies: dict[Environment, Policy]  # what the files were rendered from, for validation
    groups: list[str]
    version: str


def render_all(
    env_dir: Path = REPO_ROOT / "environments",
    directory_dir: Path = REPO_ROOT / "data" / "directory",
    version: str | None = None,
) -> Rendering:
    release = version or package_version("meridian-usage")
    groups = directory_groups(directory_dir)
    policies = {env: load_policy(Settings(app_env=env, env_dir=env_dir)) for env in ENVIRONMENTS}
    files: Files = {"deploy/README.md": README}
    for policy in policies.values():
        files |= render_environment(policy, groups, release)
    files[".claude-plugin/marketplace.json"] = _marketplace(list(policies.values()))
    return Rendering(files, policies, groups, release)
