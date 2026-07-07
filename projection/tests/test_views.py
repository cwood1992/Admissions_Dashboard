import datetime

import pandas as pd

from scripts.views import (
    REVENUE_PER_START,
    build_financial_year_view,
    build_management_view,
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
) -> dict:
    return {
        "cohort": cohort,
        "program": program,
        "days_to_start": days_to_start,
        "proj_low": proj_low,
        "proj_mid": proj_mid,
        "proj_high": proj_high,
        "wbh_count": wbh_count,
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
