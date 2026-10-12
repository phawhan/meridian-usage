from datetime import date
from decimal import Decimal

import pytest

from app.core.money import cents_to_nano, nano_to_usd, usd_to_nano
from app.core.timestamps import iso_week, month, parse_bigquery, parse_rfc3339, to_iso


def test_claude_cents_string_converts_exactly() -> None:
    assert cents_to_nano(Decimal("88.900050")) == 889_000_500  # $0.88900050


def test_gemini_dollars_convert_exactly() -> None:
    assert usd_to_nano(Decimal("0.107564")) == 107_564_000


def test_summing_nano_is_exact_where_floats_drift() -> None:
    assert sum(usd_to_nano(Decimal("0.1")) for _ in range(10)) == 10**9
    running = 0.0
    for _ in range(10):
        running += 0.1  # a running total, as a loop or SQL SUM over REAL would do
    assert running != 1.0  # why money isn't stored or summed as floats


def test_nano_to_usd_rounds_for_display_only() -> None:
    assert nano_to_usd(889_000_500) == 0.889


def test_both_timestamp_formats_normalise_to_the_same_form() -> None:
    claude = to_iso(parse_rfc3339("2026-08-06T03:41:17.882Z"))
    gemini = to_iso(parse_bigquery("2026-08-06 03:41:17.882 UTC"))
    assert claude == gemini == "2026-08-06T03:41:17.882Z"


def test_bigquery_timestamp_without_fraction_sorts_correctly_after_normalising() -> None:
    whole, fraction = (
        parse_bigquery("2026-08-06 03:41:17 UTC"),
        parse_bigquery("2026-08-06 03:41:17.5 UTC"),
    )
    assert to_iso(whole) < to_iso(fraction)


def test_timestamps_without_timezone_are_refused() -> None:
    with pytest.raises(ValueError):
        parse_rfc3339("2026-08-06T03:41:17")
    with pytest.raises(ValueError):
        parse_bigquery("2026-08-06 03:41:17")


def test_iso_week_and_month_at_window_edges() -> None:
    assert iso_week(date(2026, 8, 3)) == "2026-W32"  # first day of the data window
    assert iso_week(date(2026, 9, 27)) == "2026-W39"  # last day (a Sunday)
    assert iso_week(date(2026, 12, 31)) == "2026-W53"
    assert month(date(2026, 9, 27)) == "2026-09"
