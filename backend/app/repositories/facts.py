"""usage_fact and ingest_issue: derived data, replaced one (platform, usage_date) at a time."""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from app.repositories.raw import INGEST_ACTOR, KEY_COLUMNS, RawTable

Platform = Literal["claude", "gemini"]
IssueCode = Literal[
    "unknown_user",
    "unknown_group",
    "group_mismatch",
    "cost_pending",
    "usage_missing",
    "token_total_mismatch",
    "unknown_sku",
]


@dataclass(frozen=True)
class FactRow:
    platform: Platform
    usage_date: str
    iso_week: str
    month: str
    user_id: str
    group_id: str
    model: str
    product: str
    input_tokens: int
    output_tokens: int
    requests: int | None
    cost_nanousd: int
    metadata: dict[str, object] = field(default_factory=dict)
    raw_refs: dict[str, list[int]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class IssueRow:
    platform: Platform
    usage_date: str
    severity: Literal["error", "warning"]
    code: IssueCode
    detail: str
    raw_table: RawTable
    raw_ids: tuple[int, ...]


def replace_partitions(
    conn: sqlite3.Connection,
    platform: Platform,
    dates: list[str],
    facts: list[FactRow],
    issues: list[IssueRow],
    now: str,
) -> None:
    for table in ("usage_fact", "ingest_issue"):
        conn.executemany(
            f"DELETE FROM {table} WHERE platform = ? AND usage_date = ?",
            [(platform, day) for day in dates],
        )
    conn.executemany(
        "INSERT INTO usage_fact (platform, usage_date, iso_week, month, user_id, group_id, model,"
        " product, input_tokens, output_tokens, total_tokens, requests, cost_nanousd, metadata,"
        " raw_refs, created_at, created_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                f.platform,
                f.usage_date,
                f.iso_week,
                f.month,
                f.user_id,
                f.group_id,
                f.model,
                f.product,
                f.input_tokens,
                f.output_tokens,
                f.total_tokens,
                f.requests,
                f.cost_nanousd,
                json.dumps(f.metadata, sort_keys=True),
                json.dumps(f.raw_refs),
                now,
                INGEST_ACTOR,
            )
            for f in facts
        ],
    )
    conn.executemany(
        "INSERT INTO ingest_issue (platform, usage_date, severity, code, detail, raw_table,"
        " raw_ids, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                i.platform,
                i.usage_date,
                i.severity,
                i.code,
                i.detail,
                i.raw_table,
                json.dumps(list(i.raw_ids)),
                now,
                INGEST_ACTOR,
            )
            for i in issues
        ],
    )


def quarantined_by_file(conn: sqlite3.Connection) -> dict[int, int]:
    """Error-severity issues counted against the source_file that last wrote each raw row."""
    counts: dict[int, int] = {}
    for table in KEY_COLUMNS:
        rows = conn.execute(
            f"SELECT r.source_file_id, COUNT(*) FROM ingest_issue i, json_each(i.raw_ids) j"
            f" JOIN {table} r ON r.id = j.value"
            " WHERE i.severity = 'error' AND i.raw_table = ? GROUP BY r.source_file_id",
            (table,),
        )
        for file_id, n in rows:
            counts[file_id] = counts.get(file_id, 0) + n
    return counts
