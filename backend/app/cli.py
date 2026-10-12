"""Command line entry point: `uv run meridian sync` (APP_ENV, DB_PATH, DATA_DIR apply)."""

import argparse
from contextlib import closing

from app.core.config import Settings
from app.db.session import connect, init_db
from app.services.sync import run_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian", description="Meridian usage service")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "sync", help="take in new files under DATA_DIR (directory snapshot, usage exports)"
    )
    parser.parse_args(argv)

    settings = Settings()
    with closing(connect(settings.database_file)) as conn:
        init_db(conn, settings.app_env)
        report = run_sync(conn, settings, trigger="cli")

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
    for problem in report.problems:
        print(f"  rejected: {problem}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
