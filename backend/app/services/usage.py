"""Usage and cost by platform, group, week, month, model and product.

Access is decided before these are called (services.authz); every function takes the list
of groups the caller may see and never widens it.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

from app.core.money import nano_to_usd
from app.core.periods import DataWindow, Period
from app.models.api import (
    Breakdown,
    BreakdownRow,
    Dimension,
    PeriodOut,
    Platform,
    PlatformTotals,
    TopUser,
    Totals,
    UsageSummary,
)
from app.repositories import usage as repo

PLATFORMS: tuple[Platform, ...] = ("claude", "gemini")


def data_window(conn: sqlite3.Connection) -> DataWindow:
    bounds = repo.data_window(conn)
    if bounds is None:  # nothing ingested yet: anchor on today
        today = datetime.now(UTC).date()
        return DataWindow(start=today, end_exclusive=today)
    return DataWindow(start=bounds[0], end_exclusive=bounds[1] + timedelta(days=1))


def _period_out(period: Period, window: DataWindow) -> PeriodOut:
    return PeriodOut(
        label=period.label,
        start=period.start,
        end_exclusive=period.end_exclusive,
        complete=period.complete_within(window),
    )


def summary(
    conn: sqlite3.Connection, group_id: str, period: Period, window: DataWindow
) -> UsageSummary:
    rows = {
        r["platform"]: r
        for r in repo.aggregate(conn, [group_id], period.start, period.end_exclusive, ["platform"])
    }
    platforms = []
    for platform in PLATFORMS:  # both always present, zero when unused, for a stable shape
        row = rows.get(platform)
        platforms.append(
            PlatformTotals(
                platform=platform,
                requests=(row["requests"] if row else 0) if platform == "claude" else None,
                input_tokens=row["input_tokens"] if row else 0,
                output_tokens=row["output_tokens"] if row else 0,
                total_tokens=row["total_tokens"] if row else 0,
                cost_usd=nano_to_usd(row["cost_nanousd"]) if row else 0.0,
            )
        )
    total_nano = sum(r["cost_nanousd"] for r in rows.values())
    return UsageSummary(
        group=group_id,
        period=_period_out(period, window),
        platforms=platforms,
        totals=Totals(
            total_tokens=sum(p.total_tokens for p in platforms), cost_usd=nano_to_usd(total_nano)
        ),
    )


def breakdown(
    conn: sqlite3.Connection,
    group_ids: list[str],
    period: Period,
    window: DataWindow,
    by: list[Dimension],
) -> Breakdown:
    rows = repo.aggregate(conn, group_ids, period.start, period.end_exclusive, list(by))
    out = [
        BreakdownRow(
            **{d: row[d] for d in by},
            requests=row["requests"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            cost_usd=nano_to_usd(row["cost_nanousd"]),
        )
        for row in rows
    ]
    return Breakdown(
        period=_period_out(period, window),
        groups=group_ids,
        by=by,
        rows=out,
        totals=Totals(
            total_tokens=sum(r["total_tokens"] for r in rows),
            cost_usd=nano_to_usd(sum(r["cost_nanousd"] for r in rows)),
        ),
    )


def top_users(
    conn: sqlite3.Connection, group_ids: list[str], period: Period, limit: int
) -> list[TopUser]:
    return [
        TopUser(
            user_id=row["user_id"],
            name=row["name"],
            email=row["email"],
            group=row["group_id"],
            total_tokens=row["total_tokens"],
            cost_usd=nano_to_usd(row["cost_nanousd"]),
        )
        for row in repo.top_users(conn, group_ids, period.start, period.end_exclusive, limit)
    ]
