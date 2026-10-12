"""discover -> extract (raw) -> transform -> attribute -> load (facts) -> report.

All accepted files and the facts derived from them commit in one transaction: if anything
fails, nothing is recorded, so the next pass retries the same files. Rejected files are
recorded on their own so the rejection survives.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.core.clock import utc_now_iso
from app.repositories import facts as facts_repo
from app.repositories import raw, sync_log
from app.repositories.facts import Platform
from app.repositories.raw import INGEST_ACTOR
from app.repositories.sync_log import FileCounts
from app.services.ingestion import claude, gemini
from app.services.ingestion.attribute import DirectoryIndex
from app.services.ingestion.sources import ParsedFile, SourceFile, discover, parse

Partition = tuple[Platform, str]


@dataclass(frozen=True)
class FileOutcome:
    path: str
    status: Literal["applied", "unchanged", "rejected"]
    counts: FileCounts | None = None
    error: str | None = None


@dataclass(frozen=True)
class IngestResult:
    files: tuple[FileOutcome, ...]
    partitions_rebuilt: int
    facts: int
    errors: int
    warnings: int

    @property
    def rejected(self) -> list[FileOutcome]:
        return [f for f in self.files if f.status == "rejected"]


def _describe(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
    return str(exc)


def ingest_usage(
    conn: sqlite3.Connection, data_dir: Path, run_id: int, *, rebuild_all: bool = False
) -> IngestResult:
    """Take in new or changed export files. rebuild_all re-derives every partition, used
    when the directory changed, since attribution depends on it."""
    outcomes: list[FileOutcome] = []
    accepted: list[tuple[SourceFile, ParsedFile]] = []
    for source in discover(data_dir):
        if sync_log.latest_sha256(conn, source.path) == source.sha256:
            outcomes.append(FileOutcome(source.path, "unchanged"))
            continue
        try:
            accepted.append((source, parse(source)))
        except ValueError as exc:
            error = _describe(exc)
            with conn:
                sync_log.record_file(
                    conn,
                    run_id=run_id,
                    kind=source.layout.kind,
                    path=source.path,
                    sha256=source.sha256,
                    exported_at=None,
                    actor=INGEST_ACTOR,
                    error=error,
                )
            outcomes.append(FileOutcome(source.path, "rejected", error=error))

    now = utc_now_iso()
    with conn:
        touched: set[Partition] = set()
        file_ids: dict[str, int] = {}
        for source, parsed in accepted:
            file_id = sync_log.record_file(
                conn,
                run_id=run_id,
                kind=source.layout.kind,
                path=source.path,
                sha256=source.sha256,
                exported_at=parsed.exported_at,
                actor=INGEST_ACTOR,
            )
            result = raw.upsert(conn, source.layout.table, parsed.records, file_id=file_id, now=now)
            file_ids[source.path] = file_id
            touched |= {(source.layout.platform, day) for day in result.touched_dates}
            outcomes.append(FileOutcome(source.path, "applied", counts=result.counts))
        if rebuild_all:
            touched |= _all_partitions(conn)
        facts, errors, warnings = rebuild(conn, touched, now)

        quarantined = facts_repo.quarantined_by_file(conn)
        for i, outcome in enumerate(outcomes):
            if outcome.status == "applied" and outcome.counts is not None:
                file_id = file_ids[outcome.path]
                counts = FileCounts(
                    rows_read=outcome.counts.rows_read,
                    rows_inserted=outcome.counts.rows_inserted,
                    rows_updated=outcome.counts.rows_updated,
                    rows_quarantined=quarantined.get(file_id, 0),
                )
                sync_log.set_counts(conn, file_id, counts)
                outcomes[i] = FileOutcome(outcome.path, "applied", counts=counts)

    return IngestResult(tuple(outcomes), len(touched), facts, errors, warnings)


def _all_partitions(conn: sqlite3.Connection) -> set[Partition]:
    claude_days = raw.all_dates(conn, "raw_claude_usage") | raw.all_dates(conn, "raw_claude_cost")
    gemini_days = raw.all_dates(conn, "raw_gemini_billing")
    return {("claude", d) for d in claude_days} | {("gemini", d) for d in gemini_days}


def rebuild(conn: sqlite3.Connection, partitions: set[Partition], now: str) -> tuple[int, int, int]:
    """Re-derive facts and issues for the given (platform, day) partitions.
    Returns (facts, error issues, warning issues) written."""
    index = DirectoryIndex.load(conn)
    totals = [0, 0, 0]
    for platform in ("claude", "gemini"):
        days = sorted(day for p, day in partitions if p == platform)
        if not days:
            continue
        if platform == "claude":
            built = claude.build_facts(
                raw.load(conn, "raw_claude_usage", days),
                raw.load(conn, "raw_claude_cost", days),
                index,
            )
        else:
            built = gemini.build_facts(raw.load(conn, "raw_gemini_billing", days), index)
        facts, issues = built
        facts_repo.replace_partitions(conn, platform, days, facts, issues, now)
        totals[0] += len(facts)
        totals[1] += sum(1 for i in issues if i.severity == "error")
        totals[2] += sum(1 for i in issues if i.severity == "warning")
    return totals[0], totals[1], totals[2]
