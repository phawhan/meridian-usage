from datetime import UTC, datetime


def utc_now_iso() -> str:
    """Current time in the schema's timestamp format, e.g. 2026-10-12T09:30:00.000Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
