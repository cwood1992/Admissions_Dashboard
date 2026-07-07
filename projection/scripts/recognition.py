"""Tuition revenue recognition calendar.

Tuition is *earned* pro rata — one 150th of a cohort's revenue per day of
attendance over the 150-day program. This module answers "how many of a
cohort's 150 attendance days fall in each calendar year" so revenue can be
recognized in the year it is actually earned (not the year the class started).

Attendance-day rule (confirmed with Clanton):
    weekday (Mon-Fri)
      minus US federal holidays (with weekend observance)
      minus the Friday after Thanksgiving
      minus a winter break of Dec 25-31 (Jan 1 is the New Year federal holiday);
            first day back is the first weekday on/after Jan 2.

To change whether the school works a given federal holiday, edit
``federal_holidays`` — it is intentionally the single source of that list.
"""
from __future__ import annotations

from datetime import date, timedelta

PROGRAM_ATTENDANCE_DAYS = 150


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th `weekday` (Mon=0 … Sun=6) of a month, e.g. 3rd Monday of Jan."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last `weekday` of a month, e.g. last Monday of May."""
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observed(d: date) -> date:
    """Weekend observance for fixed-date federal holidays: Sat->Fri, Sun->Mon."""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


def federal_holidays(year: int) -> frozenset[date]:
    """Observed US federal holidays for `year`, plus the Friday after Thanksgiving.

    Fixed-date holidays (New Year, Juneteenth, Independence Day, Veterans Day,
    Christmas) are shifted to their observed weekday. Christmas and New Year also
    fall inside the winter break, but are listed here for completeness.
    """
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]

    thanksgiving = _nth_weekday(year, 11, 3, 4)  # 4th Thursday of November
    holidays = {
        _observed(date(year, 1, 1)),          # New Year's Day
        _nth_weekday(year, 1, 0, 3),           # MLK Jr. Day (3rd Mon Jan)
        _nth_weekday(year, 2, 0, 3),           # Presidents' Day (3rd Mon Feb)
        _last_weekday(year, 5, 0),             # Memorial Day (last Mon May)
        _observed(date(year, 6, 19)),          # Juneteenth
        _observed(date(year, 7, 4)),           # Independence Day
        _nth_weekday(year, 9, 0, 1),           # Labor Day (1st Mon Sep)
        _nth_weekday(year, 10, 0, 2),          # Columbus Day (2nd Mon Oct)
        _observed(date(year, 11, 11)),         # Veterans Day
        thanksgiving,                          # Thanksgiving (4th Thu Nov)
        thanksgiving + timedelta(days=1),      # Friday after Thanksgiving
        _observed(date(year, 12, 25)),         # Christmas Day
    }
    frozen = frozenset(holidays)
    _HOLIDAY_CACHE[year] = frozen
    return frozen


def _in_winter_break(d: date) -> bool:
    """Dec 25-31 winter break (Jan 1 is handled as the New Year holiday)."""
    return d.month == 12 and d.day >= 25


def is_attendance_day(d: date) -> bool:
    """True if `d` is a day tuition is earned: a weekday that is neither a
    federal holiday nor inside the winter break."""
    if d.weekday() >= 5:  # Sat/Sun
        return False
    if _in_winter_break(d):
        return False
    return d not in federal_holidays(d.year)


def attendance_days_by_year(
    start_date: date, total: int = PROGRAM_ATTENDANCE_DAYS
) -> dict[int, int]:
    """Count how many of the program's `total` attendance days fall in each
    calendar year, starting from `start_date` (which counts as day 1 if it is
    itself an attendance day). The returned counts always sum to `total`.
    """
    by_year: dict[int, int] = {}
    d = start_date
    counted = 0
    # Guard against pathological loops; 150 attendance days span < 2 years.
    while counted < total:
        if is_attendance_day(d):
            counted += 1
            by_year[d.year] = by_year.get(d.year, 0) + 1
        d += timedelta(days=1)
    return by_year


def recognize(
    start_date: date, amount: float, total: int = PROGRAM_ATTENDANCE_DAYS
) -> dict[int, float]:
    """Split `amount` across calendar years pro rata by attendance days.

    Σ of the returned per-year values equals `amount` (bar float rounding).
    """
    by_year = attendance_days_by_year(start_date, total)
    return {year: amount * days / total for year, days in by_year.items()}
