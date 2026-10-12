"""Source timestamp formats -> one form.

Claude uses RFC 3339 ("2026-08-03T00:00:00.000Z"); the GCP billing export uses BigQuery's
"2026-08-03 00:00:00 UTC", with or without fractional seconds. Both are UTC.
"""

from datetime import UTC, date, datetime


def parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp without a timezone: {value!r}")
    return parsed.astimezone(UTC)


def parse_bigquery(value: str) -> datetime:
    if not value.endswith(" UTC"):
        raise ValueError(f"expected a BigQuery UTC timestamp, got {value!r}")
    return datetime.fromisoformat(value.removesuffix(" UTC")).replace(tzinfo=UTC)


def to_iso(moment: datetime) -> str:
    """Millisecond ISO 8601 UTC, the schema's format; sorts correctly as text."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def iso_week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def month(day: date) -> str:
    return day.strftime("%Y-%m")
