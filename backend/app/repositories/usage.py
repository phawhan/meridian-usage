"""Aggregate queries over usage_fact. Callers pass only groups the caller may see; this module
doesn't check access. Money is summed as integers (nano-USD) and converted only at the edge."""

import sqlite3
from datetime import date

# Whitelisted dimension -> column. Only these names ever reach SQL.
DIMENSION_COLUMNS = {
    "platform": "platform",
    "group": "group_id",
    "week": "iso_week",
    "month": "month",
    "model": "model",
    "product": "product",
}

_MEASURES = (
    "SUM(requests) AS requests, SUM(input_tokens) AS input_tokens,"
    " SUM(output_tokens) AS output_tokens, SUM(total_tokens) AS total_tokens,"
    " SUM(cost_nanousd) AS cost_nanousd"
)


def data_window(conn: sqlite3.Connection) -> tuple[date, date] | None:
    row = conn.execute("SELECT MIN(usage_date), MAX(usage_date) FROM usage_fact").fetchone()
    if row[0] is None:
        return None
    return date.fromisoformat(row[0]), date.fromisoformat(row[1])


def _where(group_ids: list[str]) -> str:
    marks = ", ".join("?" * len(group_ids))
    return f"group_id IN ({marks}) AND usage_date >= ? AND usage_date < ?"


def aggregate(
    conn: sqlite3.Connection,
    group_ids: list[str],
    start: date,
    end_exclusive: date,
    dimensions: list[str],
) -> list[sqlite3.Row]:
    columns = [f'{DIMENSION_COLUMNS[d]} AS "{d}"' for d in dimensions]
    group_by = (
        f" GROUP BY {', '.join(DIMENSION_COLUMNS[d] for d in dimensions)}" if dimensions else ""
    )
    order_by = (
        f" ORDER BY {', '.join(DIMENSION_COLUMNS[d] for d in dimensions)}" if dimensions else ""
    )
    sql = (
        f"SELECT {', '.join([*columns, _MEASURES])} FROM usage_fact"
        f" WHERE {_where(group_ids)}{group_by}{order_by}"
    )
    return conn.execute(sql, [*group_ids, start.isoformat(), end_exclusive.isoformat()]).fetchall()


def top_users(
    conn: sqlite3.Connection, group_ids: list[str], start: date, end_exclusive: date, limit: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT f.user_id, u.name, u.email, f.group_id, SUM(f.total_tokens) AS total_tokens,"
        " SUM(f.cost_nanousd) AS cost_nanousd"
        " FROM usage_fact f JOIN users u ON u.user_id = f.user_id"
        f" WHERE {_where(group_ids)}"
        " GROUP BY f.user_id, f.group_id"
        " ORDER BY total_tokens DESC, cost_nanousd DESC, f.user_id LIMIT ?",
        [*group_ids, start.isoformat(), end_exclusive.isoformat(), limit],
    ).fetchall()
