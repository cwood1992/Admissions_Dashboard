import datetime

import pandas as pd

from scripts.views import (
    REVENUE_PER_START,
    build_financial_year_view,
    build_management_view,
    build_revenue_recognition_view,
    compute_red_flags,
    render_management_markdown,
)


def _cohort_row(
    cohort: str,
    program: str,
    days_to_start: int,
    proj_low: int,
    proj_mid: int,
    proj_high: int,
    wbh_count: int = 5,
    high_water_enrolled: int | None = None,
) -> dict:
    return {
        "cohort": cohort,
        "program": program,
        "days_to_start": days_to_start,
        "proj_low": proj_low,
        "proj_mid": proj_mid,
        "proj_high": proj_high,
        "wbh_count": wbh_count,
        "high_water_enrolled": high_water_enrolled,
    }


def _fy_inputs():
    """A minimal FY setup: one started cohort (booked actual) + two future
    cohorts (projected) in FY2026, plus one FY2027 cohort that must be excluded
    from the 2026 view. cohort_df holds only forward cohorts, as the real
    pipeline does (started cohorts drop out of the projection window)."""
    cohort_df = pd.DataFrame(
        [
            _cohort_row("UDT568", "UDT", 27, 8, 10, 12),
            _cohort_row("NDT568", "NDT-Day", 27, 14, 16, 18),
        ]
    )
    actuals_df = pd.DataFrame(
        [{"cohort": "UDT566", "program": "UDT", "actual_starts": 10}]
    )
    start_dates = {
        "UDT566": datetime.date(2026, 5, 18),  # started before snapshot
        "UDT568": datetime.date(2026, 8, 3),   # future, FY2026
        "NDT568": datetime.date(2026, 8, 3),   # future, FY2026
        "UDT572": datetime.date(2027, 1, 4),   # FY2027, excluded from 2026 view
    }
    return cohort_df, actuals_df, start_dates


def test_fy_view_blends_actuals_and_projections():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    out = build_financial_year_view(
        cohort_df, actuals_df, start_dates, 2026, "2026-07-07", "test-note"
    )
    assert out["fiscal_year"] == 2026
    t = out["total"]
    assert t["actual_starts"] == 10           # booked from UDT566
    assert t["proj_low"] == 32                # 10 + 8 + 14
    assert t["proj_mid"] == 36                # 10 + 10 + 16
    assert t["proj_high"] == 40               # 10 + 12 + 18
    assert t["proj_low"] <= t["proj_mid"] <= t["proj_high"]
    assert out["revenue_per_start"] == REVENUE_PER_START
    assert out["year_end_revenue_mid"] == 36 * REVENUE_PER_START
    udt = out["by_program"]["UDT"]
    assert udt["cohort_count"] == 2 and udt["started_count"] == 1
    assert udt["actual_starts"] == 10 and udt["proj_mid"] == 20
    assert out["by_program"]["NDT-Day"]["proj_mid"] == 16
    # UDT572 belongs to FY2027 and must not appear in the 2026 view.
    assert all(c["cohort"] != "UDT572" for c in out["cohorts"])
    assert out["model_confidence_note"] == "test-note"


def test_fy_view_started_cohorts_are_point_values():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    out = build_financial_year_view(
        cohort_df, actuals_df, start_dates, 2026, "2026-07-07", "n"
    )
    started = [c for c in out["cohorts"] if c["status"] == "actual"]
    assert started
    assert all(
        c["starts_low"] == c["starts_mid"] == c["starts_high"] == c["actual_starts"]
        for c in started
    )


def test_fy_next_year_is_projection_only():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    cohort_df = pd.concat(
        [cohort_df, pd.DataFrame([_cohort_row("UDT572", "UDT", 180, 5, 7, 9)])],
        ignore_index=True,
    )
    out = build_financial_year_view(
        cohort_df, actuals_df, start_dates, 2027, "2026-07-07", "n"
    )
    assert out["total"]["actual_starts"] == 0
    assert out["total"]["proj_mid"] == 7
    assert [c["cohort"] for c in out["cohorts"]] == ["UDT572"]


def test_recognition_view_totals_and_split():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    view = build_revenue_recognition_view(
        cohort_df, actuals_df, start_dates, "2026-07-07", "note"
    )
    # Included cohorts: UDT566 (booked actual 10), UDT568 (mid 10), NDT568 (mid 16).
    # UDT572 is future but absent from cohort_df -> no projection -> excluded.
    expected_total = (10 + 10 + 16) * REVENUE_PER_START
    year_sum = sum(view["by_year"][y]["earned_mid"] for y in view["years"])
    assert abs(year_sum - expected_total) <= 3  # whole-dollar rounding per year
    assert all(c["cohort"] != "UDT572" for c in view["cohorts"])

    for y in view["years"]:
        b = view["by_year"][y]
        assert b["earned_low"] <= b["earned_mid"] <= b["earned_high"]
        assert abs(b["earned_actual"] + b["earned_projected"] - b["earned_mid"]) <= 2

    # Booked = the one started cohort (UDT566), recognized across its year(s).
    booked_total = sum(view["by_year"][y]["earned_actual"] for y in view["years"])
    assert abs(booked_total - 10 * REVENUE_PER_START) <= 3


def test_red_flag_far_below_position_average():
    # 25 days to start, proj_mid=5, position_avg=20 → 25% of pos avg → flag.
    df = pd.DataFrame([_cohort_row("UDT566", "UDT", 25, 3, 5, 7, wbh_count=4)])
    flags = compute_red_flags(df, {"UDT566": 20})
    assert len(flags) == 1
    assert flags[0].cohort == "UDT566"
    assert "below" in flags[0].reason or "position average" in flags[0].reason


def test_red_flag_zero_wbh_under_21d():
    df = pd.DataFrame([_cohort_row("UDT566", "UDT", 15, 8, 10, 12, wbh_count=0)])
    flags = compute_red_flags(df, {"UDT566": 18})
    reasons = " ".join(f.reason for f in flags)
    assert "zero WBH" in reasons


def test_no_flag_when_healthy():
    df = pd.DataFrame([_cohort_row("UDT566", "UDT", 60, 16, 19, 22, wbh_count=8)])
    flags = compute_red_flags(df, {"UDT566": 18})
    assert flags == []


# NDT-Day ATE low as of the NDT568 backtest; WBH show rate then in effect.
_ATE_LOWS = {"NDT-Day": 0.0436, "NDT-Night": 0.2005, "UDT": 0.0846}
_WBH_RATE = 0.81


def test_red_flag_projected_start_rate_below_ate_low():
    # NDT568 at 3d out: proj_mid 5 on 123 ever enrolled = 4.1% < 4.36% low.
    df = pd.DataFrame(
        [_cohort_row("NDT568", "NDT-Day", 3, 4, 5, 6, wbh_count=5,
                     high_water_enrolled=123)]
    )
    flags = compute_red_flags(df, {"NDT568": 7}, ate_lows=_ATE_LOWS,
                              wbh_show_rate=_WBH_RATE)
    reasons = " ".join(f.reason for f in flags)
    assert "projected start rate" in reasons
    assert "historical low" in reasons


def test_red_flag_wbh_floor_below_ate_low_at_14d():
    # NDT568 at 14d out: wbh=1 on 117 pool -> floor 0.7%, but proj_mid 7 keeps
    # the implied projected rate (6.0%) above the low - only the WBH rule fires.
    df = pd.DataFrame(
        [_cohort_row("NDT568", "NDT-Day", 14, 6, 7, 9, wbh_count=1,
                     high_water_enrolled=117)]
    )
    flags = compute_red_flags(df, {"NDT568": 7}, ate_lows=_ATE_LOWS,
                              wbh_show_rate=_WBH_RATE)
    reasons = [f.reason for f in flags]
    assert any("WBH-implied start rate" in r for r in reasons)
    assert not any(r.startswith("projected start rate") for r in reasons)


def test_wbh_floor_rule_silent_beyond_14d():
    # Same weak WBH at 21d out must NOT fire (tagging often hasn't ramped yet).
    df = pd.DataFrame(
        [_cohort_row("NDT568", "NDT-Day", 21, 6, 7, 9, wbh_count=1,
                     high_water_enrolled=104)]
    )
    flags = compute_red_flags(df, {"NDT568": 7}, ate_lows=_ATE_LOWS,
                              wbh_show_rate=_WBH_RATE)
    assert not any("WBH-implied" in f.reason for f in flags)


def test_start_rate_rules_skip_small_pools():
    # NDT568NC-like: pool of 12 is below the min-pool guard; wbh=1 would fire
    # the floor rule on rate math alone, but n is too small to trust.
    df = pd.DataFrame(
        [_cohort_row("NDT568NC", "NDT-Night", 14, 4, 5, 6, wbh_count=1,
                     high_water_enrolled=12)]
    )
    flags = compute_red_flags(df, {"NDT568NC": 5}, ate_lows=_ATE_LOWS,
                              wbh_show_rate=_WBH_RATE)
    assert not any("start rate" in f.reason for f in flags)


def test_start_rate_rules_no_fire_when_healthy():
    # UDT568 at 14d out: wbh=21, pool 94 -> floor 18% and implied 21% both
    # comfortably above the 8.5% low.
    df = pd.DataFrame(
        [_cohort_row("UDT568", "UDT", 14, 18, 20, 23, wbh_count=21,
                     high_water_enrolled=94)]
    )
    flags = compute_red_flags(df, {"UDT568": 15}, ate_lows=_ATE_LOWS,
                              wbh_show_rate=_WBH_RATE)
    assert flags == []


def test_start_rate_rules_backward_compatible_without_ate():
    # Callers that don't pass ate_lows get the original two rules only.
    df = pd.DataFrame(
        [_cohort_row("NDT568", "NDT-Day", 3, 4, 5, 6, wbh_count=5,
                     high_water_enrolled=123)]
    )
    flags = compute_red_flags(df, {"NDT568": 7})
    assert not any("start rate" in f.reason for f in flags)


def test_management_view_includes_revenue_and_narrative():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    strategic = build_financial_year_view(
        cohort_df, actuals_df, start_dates, 2026, "2026-05-19", "tier rates are placeholders"
    )
    management = build_management_view(cohort_df, strategic, [], "2026-05-19")
    assert management["fiscal_year"] == 2026
    assert management["headline_starts_mid"] == strategic["total"]["proj_mid"]
    assert management["headline_actual_starts"] == strategic["total"]["actual_starts"]
    assert (
        management["headline_revenue_mid"]
        == strategic["total"]["proj_mid"] * REVENUE_PER_START
    )
    assert "2026-05-19" in management["narrative"]
    assert "financial-year" in management["narrative"]
    assert "placeholders" in management["narrative"]


def test_management_markdown_renders_flags():
    cohort_df, actuals_df, start_dates = _fy_inputs()
    flag_df = pd.concat(
        [cohort_df, pd.DataFrame([_cohort_row("UDT569", "UDT", 10, 0, 0, 1, wbh_count=0)])],
        ignore_index=True,
    )
    strategic = build_financial_year_view(
        flag_df, actuals_df, start_dates, 2026, "2026-05-19", "data-starved"
    )
    flags = compute_red_flags(flag_df, {"UDT569": 20})
    management = build_management_view(flag_df, strategic, flags, "2026-05-19")
    md = render_management_markdown(management, "2026-05-19")
    assert "# Cohort Pipeline Headline" in md
    assert "UDT569" in md
    assert "Booked to date" in md
    assert "$" in md
