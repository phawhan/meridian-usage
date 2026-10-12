"""Discover usage export files under DATA_DIR and turn them into raw records.

A file either parses completely or is rejected whole: a malformed record, a bucket that
isn't one UTC day, or two records sharing a natural key all reject the file (D17).
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from app.core.timestamps import parse_bigquery, parse_rfc3339, to_iso
from app.models.sources.claude import ClaudeBucket, ClaudeCostReport, ClaudeUsageReport
from app.models.sources.gemini import GeminiBillingRow
from app.repositories.raw import RawRecord, RawTable
from app.repositories.sync_log import SourceKind

Platform = Literal["claude", "gemini"]


@dataclass(frozen=True)
class Layout:
    pattern: str  # glob under DATA_DIR
    kind: SourceKind
    table: RawTable
    platform: Platform


# Filenames follow the API resource each export came from.
LAYOUTS = (
    Layout("claude/*user_usage_report*.json", "claude_usage", "raw_claude_usage", "claude"),
    Layout("claude/*user_cost_report*.json", "claude_cost", "raw_claude_cost", "claude"),
    Layout("gemini/*.jsonl", "gemini_billing", "raw_gemini_billing", "gemini"),
)


@dataclass(frozen=True)
class SourceFile:
    layout: Layout
    path: str  # relative to DATA_DIR's parent, e.g. data/claude/user_usage_report.json
    sha256: str
    content: bytes


@dataclass(frozen=True)
class ParsedFile:
    exported_at: str  # file's own freshness timestamp, schema format
    records: list[RawRecord]


def discover(data_dir: Path) -> list[SourceFile]:
    found = []
    for layout in LAYOUTS:
        for path in sorted(data_dir.glob(layout.pattern)):
            content = path.read_bytes()
            found.append(
                SourceFile(
                    layout=layout,
                    path=path.relative_to(data_dir.parent).as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    content=content,
                )
            )
    return found


def parse(source: SourceFile) -> ParsedFile:
    """Raises ValueError (incl. pydantic ValidationError) when the file must be rejected."""
    parse_file = _parse_claude if source.layout.platform == "claude" else _parse_gemini
    parsed = parse_file(source)
    duplicates = [key for key, n in Counter(r.key for r in parsed.records).items() if n > 1]
    if duplicates:
        raise ValueError(f"{len(duplicates)} natural key(s) appear twice, e.g. {duplicates[0]}")
    return parsed


def _claude_day(bucket: ClaudeBucket) -> str:
    start, end = parse_rfc3339(bucket.starting_at), parse_rfc3339(bucket.ending_at)
    if end - start != timedelta(days=1) or start.time() != start.min.time():
        raise ValueError(f"bucket {bucket.starting_at}..{bucket.ending_at} is not one UTC day")
    return start.date().isoformat()


def _actor_key(bucket: ClaudeBucket) -> str:
    # Non-user actors (e.g. API keys) have no user_id; keep them distinct so they're
    # quarantined as unknown users rather than merged.
    return bucket.actor.user_id or bucket.actor.email or bucket.actor.type


def _parse_claude(source: SourceFile) -> ParsedFile:
    document = json.loads(source.content)
    report: ClaudeUsageReport | ClaudeCostReport
    if source.layout.kind == "claude_usage":
        report = ClaudeUsageReport.model_validate(document)
    else:
        report = ClaudeCostReport.model_validate(document)
    refreshed = to_iso(parse_rfc3339(report.data_refreshed_at))
    records = []
    for raw, record in zip(document["data"], report.data, strict=True):
        key: tuple[str, ...] = (
            _actor_key(record),
            record.starting_at,
            record.product,
            record.model,
        )
        if source.layout.kind == "claude_cost":
            key += (raw["cost_type"],)
        records.append(
            RawRecord(
                key=key,
                usage_date=_claude_day(record),
                payload=json.dumps(raw, separators=(",", ":")),
                refreshed_at=refreshed,
            )
        )
    return ParsedFile(exported_at=refreshed, records=records)


def _parse_gemini(source: SourceFile) -> ParsedFile:
    records = []
    for number, line in enumerate(source.content.decode().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = GeminiBillingRow.model_validate(json.loads(line, parse_float=Decimal))
        except ValueError as exc:
            raise ValueError(f"line {number}: {exc}") from exc
        labels_key = json.dumps(sorted((label.key, label.value) for label in row.labels))
        start = parse_bigquery(row.usage_start_time)
        records.append(
            RawRecord(
                key=(row.project.id, row.sku.id, row.usage_start_time, labels_key, row.cost_type),
                usage_date=start.date().isoformat(),
                payload=line.strip(),
                refreshed_at=to_iso(parse_bigquery(row.export_time)),
            )
        )
    if not records:
        raise ValueError("file has no billing rows")
    return ParsedFile(exported_at=max(r.refreshed_at for r in records), records=records)
