"""`meridian-connector` entry point. stdout carries the MCP protocol, so every human-readable
message goes to stderr.

Startup refuses to serve (fail closed) unless all of these hold:
  - the permissions manifest exists, is valid, and is for the --env asked for;
  - the service at api_url runs the same environment and the same policy file (sha256) the
    manifest was rendered from, so both doors apply the same rules;
  - the user is an active directory user; their role and groups come from the directory.
"""

import logging
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import anyio
import httpx2
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from app.connector.config import ConfigError, ConnectorConfig, from_process
from app.connector.server import build_server
from app.connector.service import ServiceError, UsageService
from app.connector.tools import UsageConnector
from app.core.resources import shipped
from app.models.denial import Denial
from app.models.domain import User
from app.provisioning.manifest import PermissionsManifest, load_manifest


class StartupError(Exception):
    """The connector cannot serve safely; the message says why."""


def manifest_path(config: ConnectorConfig) -> Path:
    return config.manifest or shipped(f"deploy/{config.env}/permissions.json")


def read_manifest(config: ConnectorConfig) -> PermissionsManifest:
    path = manifest_path(config)
    if not path.is_file():
        raise StartupError(f"no permissions manifest at {path}; run `make provision`")
    try:
        manifest = load_manifest(path)
    except ValidationError as exc:
        raise StartupError(f"{path} is not a valid permissions manifest: {exc}") from exc
    if manifest.environment != config.env:
        raise StartupError(f"{path} is for {manifest.environment}, started as {config.env}")
    return manifest


async def connect(
    config: ConnectorConfig, transport: httpx2.AsyncBaseTransport | None = None
) -> tuple[UsageConnector, PermissionsManifest]:
    manifest = read_manifest(config)
    service = UsageService(config.api_url or manifest.api_url, config.user_id, transport=transport)
    try:
        health = await service.get("/healthz")
        if isinstance(health, Denial):  # /healthz takes no identity; a refusal is a misroute
            raise StartupError(f"{service.base_url} refused /healthz: {health.reason}")
        if health.get("environment") != config.env:
            raise StartupError(
                f"the service is running {health.get('environment')}, not {config.env}"
            )
        if health.get("policy_sha256") != manifest.source.sha256:
            raise StartupError(
                f"the service runs a different {manifest.source.path} than this manifest was"
                " rendered from; run `make provision` or restart the service"
            )
        periods = await service.get("/periods")
        me = await service.get("/me")
        if isinstance(me, Denial):
            raise StartupError(f"cannot start as {config.user_id}: {me.reason}")
    except (ServiceError, StartupError):
        await service.aclose()
        raise
    caller = User(
        user_id=me["user_id"],
        email=me["email"],
        name=me["name"],
        role=me["role"],
        group_ids=me["group_ids"],
        active=True,
    )
    connector = UsageConnector(caller, manifest.policy(), service)
    connector.periods = periods if isinstance(periods, dict) else {}
    return connector, manifest


def make_server(connector: UsageConnector, manifest: PermissionsManifest) -> Server[Any]:
    """The one way a server is built, for serving and for tests."""
    name, release = manifest.server_name, version("meridian-usage")
    return build_server(connector, name, release, connector.periods)


async def serve(config: ConnectorConfig) -> None:
    connector, manifest = await connect(config)
    log = logging.getLogger("meridian.connector")
    caller = connector.caller
    log.info(
        "serving %s as %s (%s, %s)",
        manifest.server_name,
        caller.name,
        caller.role,
        ", ".join(caller.group_ids),
    )
    server = make_server(connector, manifest)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await connector.service.aclose()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s: %(message)s")
    for noisy in ("httpx2", "httpcore", "mcp"):  # one line per request would bury refusals
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        config = from_process(sys.argv[1:] if argv is None else argv)
        anyio.run(serve, config)
    except (ConfigError, StartupError, ServiceError) as err:
        print(f"meridian-connector: {err}", file=sys.stderr)
        return 2 if isinstance(err, ConfigError) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
