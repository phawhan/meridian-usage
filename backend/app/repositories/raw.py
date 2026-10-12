"""Raw (bronze) tables: source records verbatim, upserted on their natural key (D17)."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.repositories.sync_log import FileCounts

INGEST_ACTOR = "system:ingest"

RawTable = Literal["raw_claude_usage", "raw_claude_cost", "raw_gemini_billing"]

# Natural-key columns per table, in the order RawRecord.key supplies them.
KEY_COLUMNS: dict[RawTable, tuple[str, ...]] = {
    "raw_claude_usage": ("actor_user_id", "bucket_start", "product", "model"),
    "raw_claude_cost": ("actor_user_id", "bucket_start", "product", "model", "cost_type"),
    "raw_gemini_billing": ("project_id", "sku_id", "usage_start_time", "labels_key", "cost_type"),
}


@dataclass(frozen=True)
class RawRecord:
    key: tuple[str, ...]
    usage_date: str  # YYYY-MM-DD, UTC
    payload: str  # the record as delivered
    refreshed_at: str  # source timestamp in schema format; newer wins


@dataclass(frozen=True)
class UpsertResult:
    counts: FileCounts
    touched_dates: frozenset[str]


def upsert(
    conn: sqlite3.Connection,
    table: RawTable,
    records: Iterable[RawRecord],
    *,
    file_id: int,
    now: str,
) -> UpsertResult:
    """Insert new keys; replace an existing key only when the incoming version is at least
    as new (by source timestamp) and actually differs. Older versions are ignored, so the
    outcome doesn't depend on the order files arrive in."""
    keys = KEY_COLUMNS[table]
    key_sql = ", ".join(keys)
    existing = {
        tuple(row[:-2]): (row[-2], row[-1])
        for row in conn.execute(f"SELECT {key_sql}, source_refreshed_at, payload FROM {table}")
    }
    inserts, updates, touched = [], [], set()
    read = 0
    for record in records:
        read += 1
        current = existing.get(record.key)
        if current is None:
            inserts.append(record)
        elif record.refreshed_at >= current[0] and record.payload != current[1]:
            updates.append(record)
        else:
            continue
        touched.add(record.usage_date)

    conn.executemany(
        f"INSERT INTO {table} ({key_sql}, usage_date, payload, source_refreshed_at,"
        " source_file_id, created_at, created_by, updated_at, updated_by)"
        f" VALUES ({', '.join('?' * len(keys))}, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                *r.key,
                r.usage_date,
                r.payload,
                r.refreshed_at,
                file_id,
                now,
                INGEST_ACTOR,
                now,
                INGEST_ACTOR,
            )
            for r in inserts
        ],
    )
    conn.executemany(
        f"UPDATE {table} SET payload = ?, source_refreshed_at = ?, source_file_id = ?,"
        f" updated_at = ?, updated_by = ? WHERE {' AND '.join(f'{k} = ?' for k in keys)}",
        [(r.payload, r.refreshed_at, file_id, now, INGEST_ACTOR, *r.key) for r in updates],
    )
    return UpsertResult(
        counts=FileCounts(rows_read=read, rows_inserted=len(inserts), rows_updated=len(updates)),
        touched_dates=frozenset(touched),
    )


def load(conn: sqlite3.Connection, table: RawTable, dates: list[str]) -> list[tuple[int, str]]:
    """(id, payload) for every raw record on the given days."""
    rows: list[tuple[int, str]] = []
    for day in dates:
        rows += [
            (row["id"], row["payload"])
            for row in conn.execute(f"SELECT id, payload FROM {table} WHERE usage_date = ?", (day,))
        ]
    return rows


def all_dates(conn: sqlite3.Connection, table: RawTable) -> set[str]:
    return {row[0] for row in conn.execute(f"SELECT DISTINCT usage_date FROM {table}")}
