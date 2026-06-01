"""Tests for cohort → position mapping.

Anchor: cohort 562 is position 1 in every program's annual cycle.
UDT/NDT-Day cycle of 10. NDT-Night cycle of 5 (every-other-numbered).
"""
import pytest

from scripts.utils import position_for_cohort, program_for_cohort


@pytest.mark.parametrize(
    "cohort,expected",
    [
        # UDT/NDT-Day cycle of 10
        ("UDT562", 1),
        ("UDT566", 5),
        ("UDT571", 10),
        ("UDT572", 1),   # wraps to next year
        ("UDT575", 4),
        ("NDT562", 1),
        ("NDT571", 10),
        ("NDT575", 4),
    ],
)
def test_day_cycle_positions(cohort, expected):
    assert position_for_cohort(cohort) == expected


@pytest.mark.parametrize(
    "cohort,expected",
    [
        # NDT-Night cycle of 5, numbers step by 2
        ("NDT562NC", 1),
        ("NDT564NC", 2),
        ("NDT566NC", 3),
        ("NDT568NC", 4),
        ("NDT570NC", 5),
        ("NDT572NC", 1),  # wraps to next year
        ("NDT574NC", 2),
    ],
)
def test_night_cycle_positions(cohort, expected):
    assert position_for_cohort(cohort) == expected


def test_unknown_prefix_raises():
    with pytest.raises(ValueError):
        position_for_cohort("XYZ566")


def test_program_for_cohort_handles_real_codes():
    assert program_for_cohort("UDT566") == "UDT"
    assert program_for_cohort("NDT566") == "NDT-Day"
    assert program_for_cohort("NDT566NC") == "NDT-Night"
