import math
from pathlib import Path

import pandas as pd
import pytest

from scripts.velocity import (
    AccumulationCurve,
    classify_velocity,
    compute_velocity,
    load_accumulation_curves,
)


@pytest.fixture
def curve() -> AccumulationCurve:
    return AccumulationCurve(
        rows=pd.DataFrame(
            [
                {"program": "UDT", "days_to_start": 0, "expected_fill_pct": 1.00, "confidence": "approximate"},
                {"program": "UDT", "days_to_start": 14, "expected_fill_pct": 0.90, "confidence": "approximate"},
                {"program": "UDT", "days_to_start": 30, "expected_fill_pct": 0.75, "confidence": "approximate"},
                {"program": "UDT", "days_to_start": 60, "expected_fill_pct": 0.40, "confidence": "approximate"},
                {"program": "UDT", "days_to_start": 90, "expected_fill_pct": 0.10, "confidence": "approximate"},
            ]
        )
    )


def test_fill_pct_endpoints(curve):
    assert curve.fill_pct("UDT", 0) == 1.00
    assert curve.fill_pct("UDT", 90) == 0.10


def test_fill_pct_clamps_outside_range(curve):
    assert curve.fill_pct("UDT", -5) == 1.00
    assert curve.fill_pct("UDT", 200) == 0.10


def test_fill_pct_linear_interpolation(curve):
    # day 64 between (60, 0.40) and (90, 0.10): slope -0.01/day → 0.36
    assert curve.fill_pct("UDT", 64) == pytest.approx(0.36, abs=1e-9)
    # day 22 between (14, 0.90) and (30, 0.75): slope -0.009375/day → 0.825
    assert curve.fill_pct("UDT", 22) == pytest.approx(0.825, abs=1e-9)


def test_fill_pct_unknown_program(curve):
    with pytest.raises(ValueError, match="No accumulation curve"):
        curve.fill_pct("ZZZ", 30)


def test_classify_velocity_bands():
    # Expected = 10, tolerance = 0.10 → on-track band is [9, 11].
    assert classify_velocity(10, 10) == "on-track"
    assert classify_velocity(9.5, 10) == "on-track"
    assert classify_velocity(11.5, 10) == "above"
    assert classify_velocity(8, 10) == "below"


def test_classify_velocity_unknown_cases():
    assert classify_velocity(float("nan"), 5) == "unknown"
    assert classify_velocity(5, float("nan")) == "unknown"
    assert classify_velocity(5, 0) == "unknown"


def test_compute_velocity_hand_computed(curve):
    # All cohorts at days_to_start=64.
    # Fill at 64 = 0.36; fill at 71 = 0.29.
    # Expected weekly velocity = position_avg * (0.36 - 0.29) = position_avg * 0.07.
    #
    # UDT566: pos_avg=18, expected = 1.26, band ±10% = [1.134, 1.386].
    #   weekly=3 → above.
    # UDT567: pos_avg=18, weekly=1 → 1 < 1.134 → below.
    # UDT568: pos_avg=100, expected=7.00, band [6.30, 7.70].
    #   weekly=7 → on-track.
    current = pd.DataFrame(
        [
            {"cohort": "UDT566", "program": "UDT", "days_to_start": 64, "total_ever_enrolled": 18},
            {"cohort": "UDT567", "program": "UDT", "days_to_start": 64, "total_ever_enrolled": 16},
            {"cohort": "UDT568", "program": "UDT", "days_to_start": 64, "total_ever_enrolled": 50},
        ]
    )
    prior = pd.DataFrame(
        [
            {"cohort": "UDT566", "total_ever_enrolled": 15},
            {"cohort": "UDT567", "total_ever_enrolled": 15},
            {"cohort": "UDT568", "total_ever_enrolled": 43},
        ]
    )
    pos = {"UDT566": 18, "UDT567": 18, "UDT568": 100}
    out = compute_velocity(current, prior, curve, pos).set_index("cohort")

    assert out.loc["UDT566", "weekly_velocity"] == 3
    assert out.loc["UDT566", "expected_weekly_velocity"] == pytest.approx(1.26, abs=1e-6)
    assert out.loc["UDT566", "velocity_vs_historical"] == "above"

    assert out.loc["UDT567", "weekly_velocity"] == 1
    assert out.loc["UDT567", "velocity_vs_historical"] == "below"

    assert out.loc["UDT568", "weekly_velocity"] == 7
    assert out.loc["UDT568", "expected_weekly_velocity"] == pytest.approx(7.00, abs=1e-6)
    assert out.loc["UDT568", "velocity_vs_historical"] == "on-track"


def test_compute_velocity_missing_prior_yields_nan(curve):
    current = pd.DataFrame(
        [{"cohort": "NEW599", "program": "UDT", "days_to_start": 80, "total_ever_enrolled": 4}]
    )
    prior = pd.DataFrame([{"cohort": "OTHER", "total_ever_enrolled": 1}])
    pos = {"NEW599": 18}
    out = compute_velocity(current, prior, curve, pos).set_index("cohort")
    assert math.isnan(out.loc["NEW599", "weekly_velocity"])
    assert out.loc["NEW599", "velocity_vs_historical"] == "unknown"


def test_production_curve_file_loads():
    curve = load_accumulation_curves()
    for program in ("UDT", "NDT-Day", "NDT-Night"):
        assert curve.fill_pct(program, 30) > 0
        assert curve.fill_pct(program, 0) >= curve.fill_pct(program, 90)
    # Confidence flag is preserved so downstream basis strings can surface it.
    assert (curve.rows["confidence"] == "approximate").all()


def test_classify_velocity_from_snapshot_no_prior_needed(curve):
    # EnrollList path: weekly_velocity already on the frame. No prior snapshot.
    from scripts.velocity import classify_velocity_from_snapshot

    df = pd.DataFrame(
        [
            {"cohort": "UDT566", "program": "UDT", "days_to_start": 64, "weekly_velocity": 3},
            {"cohort": "UDT567", "program": "UDT", "days_to_start": 64, "weekly_velocity": 0},
        ]
    )
    pos = {"UDT566": 18, "UDT567": 18}
    out = classify_velocity_from_snapshot(df, curve, pos).set_index("cohort")
    # Expected weekly velocity at day 64 (same math as the legacy test) = 1.26.
    assert out.loc["UDT566", "expected_weekly_velocity"] == pytest.approx(1.26, abs=1e-6)
    assert out.loc["UDT566", "velocity_vs_historical"] == "above"   # 3 > 1.386
    assert out.loc["UDT567", "velocity_vs_historical"] == "below"   # 0 < 1.134


def test_classify_velocity_from_snapshot_handles_missing_days(curve):
    from scripts.velocity import classify_velocity_from_snapshot

    df = pd.DataFrame(
        [{"cohort": "UDT566", "program": "UDT", "days_to_start": float("nan"), "weekly_velocity": 2}]
    )
    out = classify_velocity_from_snapshot(df, curve, {"UDT566": 18}).set_index("cohort")
    assert out.loc["UDT566", "velocity_vs_historical"] == "unknown"
