import pandas as pd

from scripts.views import (
    REVENUE_PER_START,
    build_management_view,
    build_strategic_view,
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


def test_strategic_sums_and_revenue():
    df = pd.DataFrame(
        [
            _cohort_row("UDT566", "UDT", 60, 10, 12, 14),
            _cohort_row("UDT567", "UDT", 90, 8, 10, 12),
            _cohort_row("NDTD566", "NDT-Day", 45, 14, 16, 18),
        ]
    )
    out = build_strategic_view(df, "test-confidence-note")
    assert out["year_end_proj_low"] == 32
    assert out["year_end_proj_mid"] == 38
    assert out["year_end_proj_high"] == 44
    assert out["revenue_per_start"] == REVENUE_PER_START
    assert out["year_end_revenue_mid"] == 38 * REVENUE_PER_START
    assert out["by_program"]["UDT"]["proj_mid"] == 22
    assert out["by_program"]["NDT-Day"]["proj_mid"] == 16
    assert out["model_confidence_note"] == "test-confidence-note"


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
    df = pd.DataFrame([_cohort_row("UDT566", "UDT", 60, 16, 19, 22)])
    strategic = build_strategic_view(df, "tier rates are placeholders")
    management = build_management_view(df, strategic, [], "2026-05-19")
    assert management["headline_starts_mid"] == 19
    assert management["headline_revenue_mid"] == 19 * REVENUE_PER_START
    assert "2026-05-19" in management["narrative"]
    assert "placeholders" in management["narrative"]


def test_management_markdown_renders_flags():
    df = pd.DataFrame([_cohort_row("UDT566", "UDT", 10, 0, 0, 1, wbh_count=0)])
    strategic = build_strategic_view(df, "data-starved")
    flags = compute_red_flags(df, {"UDT566": 20})
    management = build_management_view(df, strategic, flags, "2026-05-19")
    md = render_management_markdown(management, "2026-05-19")
    assert "# Cohort Pipeline Headline" in md
    assert "UDT566" in md
    assert "$" in md
