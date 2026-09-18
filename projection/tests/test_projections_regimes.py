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
        vip_priority_conversion_rate=0.50,
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
    # currently=8, fill_pct=0.40 → proj_enrolled=20.0 → x ate.mid 0.115 = 2.3 starts
    # blended = (1/3)*2.3 + (2/3)*18 = 0.767 + 12 = 12.767
    # spread = (0.14-0.09)/0.115 = 0.4348; half = 0.2174
    # low = round(12.767 * 0.7826) = 10
    # mid = round(12.767)          = 13
    # high = round(12.767 * 1.2174) = 16
    proj = project_three_regime(_row(days_to_start=60), 18, ate, curve, tiers)
    assert proj.projection_basis.startswith(REGIME_FAR)
    assert "starts" in proj.projection_basis
    assert (proj.proj_low, proj.proj_mid, proj.proj_high) == (10, 13, 16)


def test_far_regime_lower_fill_curve_raises_projection(ate, tiers):
    """The curve must actually influence the far regime: a less-filled curve
    at the same enrollment means more enrollment still to come → more starts.
    (Pre-fix the cap always bound and every far cohort sat at 1.5x pos_avg.)"""
    def _curve(fill_at_60: float) -> AccumulationCurve:
        return AccumulationCurve(rows=pd.DataFrame([
            {"program": "UDT", "days_to_start": 0, "expected_fill_pct": 1.0, "confidence": "approximate"},
            {"program": "UDT", "days_to_start": 60, "expected_fill_pct": fill_at_60, "confidence": "approximate"},
            {"program": "UDT", "days_to_start": 90, "expected_fill_pct": 0.2, "confidence": "approximate"},
        ]))
    # 80/0.40 = 200 enrolled x 0.115 = 23.0 starts → blended 7.667+12 = 19.67 → 20
    # 80/0.30 = 266.7 enrolled x 0.115 = 30.67 starts → blended 10.22+12 = 22.22 → 22
    hi_fill = project_three_regime(_row(days_to_start=60, currently_enrolled=80), 18, ate, _curve(0.40), tiers)
    lo_fill = project_three_regime(_row(days_to_start=60, currently_enrolled=80), 18, ate, _curve(0.30), tiers)
    assert hi_fill.proj_mid == 20
    assert lo_fill.proj_mid == 22
    assert "capped" not in lo_fill.projection_basis


def test_far_regime_uses_high_water_when_present(curve, ate, tiers):
    # high_water 16 vs currently 8 at 60d: 16/0.40 = 40 x 0.115 = 4.6 starts
    # blended = 1.533 + 12 = 13.53 → mid 14 (vs 13 on currently_enrolled alone)
    proj = project_three_regime(
        _row(days_to_start=60, currently_enrolled=8, high_water_enrolled=16), 18, ate, curve, tiers
    )
    assert proj.proj_mid == 14


def test_far_regime_below_fill_floor_uses_position_avg_only(curve, ate, tiers):
    # fill at 90d = 0.10 < 0.15 floor → blended = pos_avg 18 regardless of enrollment.
    # spread half = 0.2174 → low round(14.09)=14, mid 18, high round(21.91)=22
    for current in (0, 5, 40):
        proj = project_three_regime(_row(days_to_start=90, currently_enrolled=current), 18, ate, curve, tiers)
        assert proj.projection_basis.startswith(REGIME_FAR)
        assert "floor" in proj.projection_basis
        assert (proj.proj_low, proj.proj_mid, proj.proj_high) == (14, 18, 22)


def test_far_regime_cap_binds_in_starts_units(curve, ate, tiers):
    # 1000/0.40 = 2500 enrolled x 0.115 = 287.5 starts > cap 2.5*18 = 45 → capped
    # blended = 15 + 12 = 27
    proj = project_three_regime(_row(days_to_start=60, currently_enrolled=1000), 18, ate, curve, tiers)
    assert "capped" in proj.projection_basis
    assert proj.proj_mid == 27


def test_far_regime_blend_uses_position_prior_weight(curve, ate, tiers):
    # Sanity-check the constant didn't drift.
    assert POSITION_PRIOR_WEIGHT == pytest.approx(2 / 3)


def test_medium_regime_selected_at_21_days(curve, ate, tiers):
    # days=21, currently=14, pos_avg=18, WBH=6, VIP=3, Priority=1
    # fill at 21 = 0.834375. proj_enrolled = 14/0.834375 = 16.779
    # x ate.mid 0.115 = 1.930 starts
    # blended = (1/3)*1.930 + (2/3)*18 = 12.643
    # far spread/2 = 0.2174
    # far_low = round(12.643 * 0.7826) = 10
    # far_mid = round(12.643) = 13
    # far_high = round(12.643 * 1.2174) = 15
    # VIP+Priority pooled = 3 + 1 = 4
    # tier_low = 6*0.90 = 5.4
    # tier_mid = 5.4 + 4*0.50 = 7.4
    # tier_high = 5.4 + 4 = 9.4 (every pooled student shows)
    # blend (avg of far and tier):
    # low = round((10+5.4)/2) = round(7.7) = 8
    # mid = round((13+7.4)/2) = round(10.2) = 10
    # high = round((15+9.4)/2) = round(12.2) = 12
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
    assert (proj.proj_low, proj.proj_mid, proj.proj_high) == (8, 10, 12)
    assert "placeholders" in proj.projection_basis


def test_near_regime_selected_at_7_days(curve, ate, tiers):
    # WBH=8, VIP=2, Priority=1 -> pooled 3; placeholder rates 0.90/0.50
    # floor = 8*0.90 = 7.2 -> round 7
    # mid = 7.2 + 3*0.50 = 8.7 -> round 9
    # high = 7.2 + 3 = 10.2 -> round 10 (every pooled student shows)
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
    assert proj.proj_mid == 9
    assert proj.proj_high == 10


def test_pooled_count_preferred_over_per_flag_sum(curve, ate, tiers):
    # 3 students carry both VIP and P-FA: per-flag sum is 6, students are 3.
    proj = project_three_regime(
        _row(days_to_start=7, wbh_count=0, vip_count=3, p_fa_count=3, vip_priority_count=3),
        18, ate, curve, tiers,
    )
    # mid = 3 * 0.50 = 1.5 -> round 2 (banker's), not 6 * 0.50 = 3
    assert proj.proj_mid == 2
    assert "VIP+Priority(3)" in proj.projection_basis


def test_near_regime_counts_priority_same_as_vip(curve, ate, tiers):
    # VIP and P-xx are one pooled tier: swapping one for the other is a no-op.
    as_vip = project_three_regime(
        _row(days_to_start=7, wbh_count=4, vip_count=4), 18, ate, curve, tiers
    )
    as_priority = project_three_regime(
        _row(days_to_start=7, wbh_count=4, p_fa_count=2, p_adm_count=2), 18, ate, curve, tiers
    )
    assert (as_vip.proj_low, as_vip.proj_mid, as_vip.proj_high) == (
        as_priority.proj_low, as_priority.proj_mid, as_priority.proj_high
    )


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
