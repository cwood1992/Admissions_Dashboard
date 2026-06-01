"""Tests for the M5 three-regime projection model.

The trivial M3 model still lives in `project_trivial` and is exercised by
test_projections_trivial.py — its unit tests still pass. This file exercises
the production three-regime model.
"""
import pandas as pd
import pytest

from scripts.projections import (
    AteRange,
    ConfidenceTierRates,
    POSITION_PRIOR_WEIGHT,
    REGIME_FAR,
    REGIME_MEDIUM,
    REGIME_NEAR,
    project_three_regime,
)
from scripts.velocity import AccumulationCurve


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


@pytest.fixture
def ate() -> AteRange:
    return AteRange(low=0.09, mid=0.115, high=0.14)


@pytest.fixture
def tiers() -> ConfidenceTierRates:
    return ConfidenceTierRates(
        wbh_show_rate=0.90,
        vip_conversion_rate=0.50,
        priority_conversion_rate=0.30,
        is_placeholder=True,
    )


def _row(**overrides) -> pd.Series:
    defaults = {
        "cohort": "UDT566",
        "program": "UDT",
        "days_to_start": 60,
        "currently_enrolled": 8,
        "wbh_count": 0,
        "vip_count": 0,
        "p_fa_count": 0,
        "p_va_count": 0,
        "p_act_count": 0,
        "p_adm_count": 0,
    }
    defaults.update(overrides)
    return pd.Series(defaults)


def test_far_regime_selected_at_60_days(curve, ate, tiers):
    # currently=8, fill_pct=0.40 → raw_proj=20.0
    # blended = (1/3)*20 + (2/3)*18 = 6.667 + 12 = 18.67
    # spread = (0.14-0.09)/0.115 = 0.4348; half = 0.2174
    # low = round(18.67 * 0.7826) = 15
    # mid = round(18.67)         = 19
    # high = round(18.67 * 1.2174) = 23
    proj = project_three_regime(_row(days_to_start=60), 18, ate, curve, tiers)
    assert proj.projection_basis.startswith(REGIME_FAR)
    assert (proj.proj_low, proj.proj_mid, proj.proj_high) == (15, 19, 23)


def test_far_regime_blend_uses_position_prior_weight(curve, ate, tiers):
    # Sanity-check the constant didn't drift.
    assert POSITION_PRIOR_WEIGHT == pytest.approx(2 / 3)


def test_medium_regime_selected_at_21_days(curve, ate, tiers):
    # days=21, currently=14, pos_avg=18, WBH=6, VIP=3, Priority=1
    # fill at 21 = 0.834. raw_proj = 14/0.834 = 16.787
    # blended = (1/3)*16.787 + (2/3)*18 = 17.596
    # far spread/2 = 0.2174
    # far_low = round(17.596 * 0.7826) = 14
    # far_mid = round(17.596) = 18
    # far_high = round(17.596 * 1.2174) = 21
    # tier_low = 6*0.90 = 5.4
    # tier_mid = 5.4 + 3*0.50 = 6.9
    # tier_high = 6.9 + 1*0.30 = 7.2
    # blend (avg of far and tier):
    # low = round((14+5.4)/2) = round(9.7) = 10
    # mid = round((18+6.9)/2) = round(12.45) = 12
    # high = round((21+7.2)/2) = round(14.1) = 14
    proj = project_three_regime(
        _row(
            days_to_start=21,
            currently_enrolled=14,
            wbh_count=6,
            vip_count=3,
            p_fa_count=1,
        ),
        18,
        ate,
        curve,
        tiers,
    )
    assert proj.projection_basis.startswith(REGIME_MEDIUM)
    assert (proj.proj_low, proj.proj_mid, proj.proj_high) == (10, 12, 14)
    assert "placeholders" in proj.projection_basis


def test_near_regime_selected_at_7_days(curve, ate, tiers):
    # WBH=8, VIP=2, Priority=1, placeholder rates 0.90/0.50/0.30
    # floor = 8*0.90 = 7.2 → round 7
    # mid = 7.2 + 2*0.50 = 8.2 → round 8
    # high = 8.2 + 1*0.30 = 8.5 → round 8, but order requires ≥ mid → 8
    # Actually round(8.5) is banker's rounding in Python 3: round(8.5)=8.
    # So enforce_order may leave high=mid=8, which still satisfies low<=mid<=high.
    proj = project_three_regime(
        _row(
            days_to_start=7,
            currently_enrolled=10,
            wbh_count=8,
            vip_count=2,
            p_fa_count=1,
        ),
        18,
        ate,
        curve,
        tiers,
    )
    assert proj.projection_basis.startswith(REGIME_NEAR)
    assert proj.proj_low == 7
    assert proj.proj_mid == 8
    assert proj.proj_high == 8


def test_near_regime_zero_wbh_yields_zero_floor(curve, ate, tiers):
    # The escalation in the spec: "Zero WBH students in a cohort under 21 days
    # from start → immediate flag." The model itself must produce 0 for the
    # floor so the flag logic downstream can detect it.
    proj = project_three_regime(
        _row(days_to_start=10, wbh_count=0, vip_count=0),
        18,
        ate,
        curve,
        tiers,
    )
    assert proj.proj_low == 0


def test_regime_threshold_boundaries(curve, ate, tiers):
    # 30 days exactly → far. 14 days exactly → medium. 13 days → near.
    far = project_three_regime(_row(days_to_start=30), 18, ate, curve, tiers)
    medium = project_three_regime(_row(days_to_start=14), 18, ate, curve, tiers)
    near = project_three_regime(_row(days_to_start=13), 18, ate, curve, tiers)
    assert far.projection_basis.startswith(REGIME_FAR)
    assert medium.projection_basis.startswith(REGIME_MEDIUM)
    assert near.projection_basis.startswith(REGIME_NEAR)


def test_missing_baseline_falls_back_to_trivial(curve, ate, tiers):
    proj = project_three_regime(_row(days_to_start=60), position_avg=None, ate=None, curve=curve, tiers=tiers)
    assert "trivial" in proj.projection_basis
    assert "no baseline" in proj.projection_basis


def test_invariant_low_le_mid_le_high_all_regimes(curve, ate, tiers):
    for days in (5, 10, 13, 14, 21, 29, 30, 45, 60, 90, 120):
        for current in (0, 3, 10, 25):
            proj = project_three_regime(
                _row(days_to_start=days, currently_enrolled=current, wbh_count=3, vip_count=2, p_fa_count=1),
                18,
                ate,
                curve,
                tiers,
            )
            assert proj.proj_low <= proj.proj_mid <= proj.proj_high, (days, current, proj)
