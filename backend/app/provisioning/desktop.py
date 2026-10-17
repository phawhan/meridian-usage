"""Register the connector in Claude Desktop on this machine: `make register-desktop`.

Takes the rendered entry from deploy/<env>/claude_desktop_config.json, fills in the user, and
merges it into Claude Desktop's config without touching other servers (a backup is written
first). Two machine-specific changes are made here, and only here, because the committed file
can't know them: the absolute path of uv/uvx (Claude Desktop starts servers with a minimal
PATH), and, with --source local, running this checkout instead of the pinned release.
"""

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from app.models.sources.directory import UsersFile
from app.provisioning.render import DESKTOP_USER_PLACEHOLDER, ENVIRONMENTS

DESKTOP_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"


class RegistrationError(Exception):
    pass


def desktop_entry(env: str, user_id: str, source: str, root: Path = REPO_ROOT) -> tuple[str, Any]:
    rendered = json.loads((root / f"deploy/{env}/claude_desktop_config.json").read_text())
    name, entry = next(iter(rendered["mcpServers"].items()))
    users = UsersFile.model_validate_json((root / "data/directory/users.json").read_text())
    if user_id not in {u.user_id for u in users.users}:
        raise RegistrationError(f"{user_id!r} is not a user in data/directory/users.json")
    args = [user_id if a == DESKTOP_USER_PLACEHOLDER else a for a in entry["args"]]
    if source == "local":  # this checkout, through its own environment
        start = args.index("meridian-connector")
        uv = shutil.which("uv")
        if uv is None:
            raise RegistrationError("uv is not on PATH")
        return name, {
            "command": uv,
            "args": ["run", "--project", str(root / "backend"), *args[start:]],
        }
    uvx = shutil.which("uvx")
    if uvx is None:
        raise RegistrationError("uvx is not on PATH")
    return name, {"command": uvx, "args": args}


def merge(existing: dict[str, Any], name: str, entry: Any) -> dict[str, Any]:
    """The same config with one server added or replaced; every other key kept."""
    servers = dict(existing.get("mcpServers", {}))
    servers[name] = entry
    return existing | {"mcpServers": servers}


def register(env: str, user_id: str, source: str, config: Path) -> str:
    name, entry = desktop_entry(env, user_id, source)
    current = json.loads(config.read_text()) if config.is_file() else {}
    if config.is_file():
        backup = config.with_name(f"{config.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(config, backup)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(merge(current, name, entry), indent=2) + "\n")
    return name


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--user", required=True, help="directory user_id to act as")
    parser.add_argument(
        "--source",
        choices=("release", "local"),
        default="release",
        help="release: the pinned tag from GitHub (default); local: this checkout",
    )
    parser.add_argument("--config", type=Path, default=DESKTOP_CONFIG)


def run(args: argparse.Namespace) -> int:
    try:
        name = register(args.env, args.user, args.source, args.config)
    except RegistrationError as err:
        print(f"register-desktop: {err}")
        return 1
    print(f"register-desktop: '{name}' now starts as {args.user} ({args.source}) in {args.config}")
    print("Quit and reopen Claude Desktop to load it.")
    return 0
