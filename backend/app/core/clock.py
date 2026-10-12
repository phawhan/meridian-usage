from datetime import UTC, datetime

from app.core.timestamps import to_iso


def utc_now_iso() -> str:
    """Current time in the schema's timestamp format, e.g. 2026-10-12T09:30:00.000Z."""
    return to_iso(datetime.now(UTC))
