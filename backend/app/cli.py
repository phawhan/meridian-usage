"""Command line entry point (APP_ENV, DB_PATH, DATA_DIR apply): `uv run meridian <command>`
with sync, serve, provision [--check] or register-desktop."""

import argparse
from contextlib import closing
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.env_config import load_policy
from app.db.session import connect, init_db
from app.provisioning import desktop
from app.provisioning.command import provision
from app.services.sync import run_sync


def serve(reload: bool) -> int:
    """The port comes from environments/<APP_ENV>.yaml (host.api_url), where the connector
    will look for this service."""
    import uvicorn

    url = urlsplit(load_policy(Settings()).api_url)
    uvicorn.run(
        "app.main:app", host=url.hostname or "127.0.0.1", port=url.port or 80, reload=reload
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian", description="Meridian usage service")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "sync", help="take in new files under DATA_DIR (directory snapshot, usage exports)"
    )
    provision_cmd = commands.add_parser(
        "provision", help="render and validate every environment's permissions and host config"
    )
    provision_cmd.add_argument(
        "--check", action="store_true", help="fail if the committed files differ; write nothing"
    )
    serve_cmd = commands.add_parser("serve", help="run the API on this environment's api_url")
    serve_cmd.add_argument("--reload", action="store_true")
    desktop.add_arguments(
        commands.add_parser("register-desktop", help="add the connector to Claude Desktop")
    )
    args = parser.parse_args(argv)
    if args.command == "provision":
        return provision(check=args.check)
    if args.command == "register-desktop":
        return desktop.run(args)
    if args.command == "serve":
        return serve(reload=args.reload)

    settings = Settings()
    policy = load_policy(settings)
    with closing(connect(settings.database_file)) as conn:
        init_db(conn, settings.app_env)
        report = run_sync(conn, settings, policy, trigger="cli")

    result = report.directory
    print(f"[{settings.app_env}] sync run {report.run_id}: directory {result.status}")
    for label, counts in (("users", result.users), ("groups", result.groups)):
        if counts:
            print(
                f"  {label}: read {counts.rows_read}, inserted {counts.rows_inserted},"
                f" updated {counts.rows_updated}, deactivated {counts.rows_deactivated}"
            )
    for file in report.usage.files:
        line = f"{file.path}: {file.status}"
        if file.counts:
            c = file.counts
            line += (
                f" (read {c.rows_read}, inserted {c.rows_inserted}, updated {c.rows_updated},"
                f" quarantined {c.rows_quarantined})"
            )
        print(f"  {line}")
    usage = report.usage
    print(
        f"  facts: {usage.facts} rebuilt across {usage.partitions_rebuilt} day partitions;"
        f" issues: {usage.errors} errors, {usage.warnings} warnings"
    )
    print(f"  capability switches seeded: {report.switches_seeded} ({policy.path})")
    for problem in report.problems:
        print(f"  rejected: {problem}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
