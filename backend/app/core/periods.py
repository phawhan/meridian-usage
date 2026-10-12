"""Reporting periods -> half-open UTC date ranges [start, end_exclusive).

Accepted forms (contracts/tools.schema.json Period): last_7_days, last_30_days, an ISO week
(2026-W36) or a calendar month (2026-09). Relative periods are anchored to the end of the
data window (the day after the newest usage day), not the wall clock (D4): with exports that
end 2026-09-27, "last 7 days" is 2026-09-21..2026-09-27 whatever today is.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

PERIOD_PATTERN = r"^(last_7_days|last_30_days|\d{4}-W\d{2}|\d{4}-\d{2})$"
_WEEK = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_RELATIVE = {"last_7_days": 7, "last_30_days": 30}


class PeriodError(ValueError):
    """Not a period this service understands."""


@dataclass(frozen=True)
class DataWindow:
    start: date  # oldest usage day
    end_exclusive: date  # day after the newest usage day; anchor for relative periods


@dataclass(frozen=True)
class Period:
    label: str
    start: date
    end_exclusive: date

    def complete_within(self, window: DataWindow) -> bool:
        """True when the data covers the whole period (2026-09 is partial: data ends the 27th)."""
        return window.start <= self.start and self.end_exclusive <= window.end_exclusive


def resolve(label: str, window: DataWindow) -> Period:
    if label in _RELATIVE:
        end = window.end_exclusive
        return Period(label, end - timedelta(days=_RELATIVE[label]), end)
    if week := _WEEK.match(label):
        try:
            monday = date.fromisocalendar(int(week[1]), int(week[2]), 1)
        except ValueError as exc:
            raise PeriodError(f"{label!r} is not a valid ISO week") from exc
        return Period(label, monday, monday + timedelta(days=7))
    if month := _MONTH.match(label):
        year, number = int(month[1]), int(month[2])
        if not 1 <= number <= 12:
            raise PeriodError(f"{label!r} is not a valid month")
        first = date(year, number, 1)
        following = date(year + number // 12, number % 12 + 1, 1)
        return Period(label, first, following)
    raise PeriodError(
        f"{label!r} is not a period; use last_7_days, last_30_days, YYYY-Www or YYYY-MM"
    )
