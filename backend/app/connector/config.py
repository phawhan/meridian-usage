"""Startup configuration. Identity is fixed here, once, from the command line or the host's
environment block, and never from a tool argument: a prompt can change which group is asked
about but not who is asking.
"""

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast, get_args

from app.core.config import Environment


class ConfigError(ValueError):
    """A required setting is missing or invalid; the connector refuses to start."""


@dataclass(frozen=True)
class ConnectorConfig:
    user_id: str
    env: Environment
    manifest: Path | None  # None: the one rendered for env (deploy/<env>/permissions.json)
    api_url: str | None  # overrides the manifest's api_url when set


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="meridian-connector",
        description="Meridian usage MCP server (stdio). Each flag may instead come from "
        "MERIDIAN_USER, MERIDIAN_ENV, MERIDIAN_MANIFEST, MERIDIAN_API_URL.",
        allow_abbrev=False,  # '--us' must not quietly mean '--user'
    )
    p.add_argument("--user", help="directory user_id the server acts as")
    p.add_argument("--env", help="dev | staging | prod")
    p.add_argument("--manifest", help="permissions manifest (default: the one rendered for --env)")
    p.add_argument("--api-url", help="Part A service base URL (default: from the manifest)")
    return p


def parse_config(argv: Sequence[str], environ: Mapping[str, str]) -> ConnectorConfig:
    """Flags win over environment variables. Raises ConfigError naming every missing setting."""
    args = _parser().parse_args(argv)
    user = args.user or environ.get("MERIDIAN_USER") or None
    env = args.env or environ.get("MERIDIAN_ENV") or None
    manifest = args.manifest or environ.get("MERIDIAN_MANIFEST") or None
    api_url = args.api_url or environ.get("MERIDIAN_API_URL") or None

    required = (("--user", user), ("--env", env))
    missing = [flag for flag, value in required if not value]
    if missing:
        raise ConfigError(f"missing {', '.join(missing)}")
    if env not in get_args(Environment):
        raise ConfigError(f"--env must be one of {', '.join(get_args(Environment))}, got {env!r}")
    assert user
    path = Path(manifest) if manifest else None
    return ConnectorConfig(user, cast(Environment, env), path, api_url)


def from_process(argv: Sequence[str]) -> ConnectorConfig:
    return parse_config(argv, os.environ)
