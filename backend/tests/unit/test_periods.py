from datetime import date

import pytest

from app.core.periods import DataWindow, PeriodError, resolve

# The starter data: 2026-08-03 (Mon, W32) to 2026-09-27 (Sun, W39) inclusive.
WINDOW = DataWindow(start=date(2026, 8, 3), end_exclusive=date(2026, 9, 28))


@pytest.mark.parametrize(
    ("label", "start", "end_exclusive"),
    [
        ("last_7_days", date(2026, 9, 21), date(2026, 9, 28)),
        ("last_30_days", date(2026, 8, 29), date(2026, 9, 28)),
        ("2026-W36", date(2026, 8, 31), date(2026, 9, 7)),
        ("2026-W32", date(2026, 8, 3), date(2026, 8, 10)),
        ("2026-08", date(2026, 8, 1), date(2026, 9, 1)),
        ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),
        ("2026-W53", date(2026, 12, 28), date(2027, 1, 4)),  # 2026 has 53 ISO weeks
    ],
)
def test_periods_resolve_to_half_open_ranges(label: str, start: date, end_exclusive: date) -> None:
    period = resolve(label, WINDOW)
    assert (period.start, period.end_exclusive) == (start, end_exclusive)


def test_relative_periods_follow_the_data_not_the_clock() -> None:
    later = DataWindow(start=date(2026, 8, 3), end_exclusive=date(2026, 11, 1))
    assert resolve("last_7_days", later).start == date(2026, 10, 25)


@pytest.mark.parametrize(
    ("label", "complete"),
    [("2026-W39", True), ("2026-09", False), ("2026-08", False), ("last_30_days", True)],
)
def test_partial_coverage_is_flagged(label: str, complete: bool) -> None:
    # 2026-08 is partial too: data starts on the 3rd.
    assert resolve(label, WINDOW).complete_within(WINDOW) is complete


@pytest.mark.parametrize("label", ["2026-W54", "2026-W00", "2026-13", "2026-00", "yesterday", ""])
def test_invalid_periods_are_refused(label: str) -> None:
    with pytest.raises(PeriodError):
        resolve(label, WINDOW)
