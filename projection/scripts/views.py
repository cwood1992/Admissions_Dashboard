"""Audience-specific view builders.

The same underlying snapshot drives four outputs:
- Thomas: cohort table with operational flags + rep scorecards.
- Rep: per-rep aggregate view (no PII; counts only).
- Clanton: strategic year-end projection, revenue, model confidence.
- Management: 3-number headline + one-paragraph narrative + red flags.

Each builder takes the cohort DataFrame (post-projections) plus optional rep
scorecards and returns a dict for JSON serialization and/or a markdown string.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from scripts import recognition, utils

REVENUE_PER_START = 25_300  # Per spec, blended UDT/NDT-Day/NDT-Night.
PROGRAM_ORDER = ["UDT", "NDT-Day", "NDT-Night"]

RED_FLAG_MID_VS_POS_AVG_BELOW = 0.50  # proj_mid < 50% of position_avg
RED_FLAG_NEAR_DAYS = 30
ZERO_WBH_NEAR_DAYS = 21


@dataclass(frozen=True)
class RedFlag:
    cohort: str
    program: str
    days_to_start: int
    proj_mid: int
    reason: str


def compute_red_flags(
    cohort_df: pd.DataFrame,
    position_averages: dict[str, int],
) -> list[RedFlag]:
    flags: list[RedFlag] = []
    for _, row in cohort_df.iterrows():
        days = int(row["days_to_start"])
        cohort = str(row["cohort"])
        program = str(row["program"])
        proj_mid = int(row["proj_mid"])
        pos_avg = position_averages.get(cohort)

        if days <= RED_FLAG_NEAR_DAYS and pos_avg:
            if proj_mid < pos_avg * RED_FLAG_MID_VS_POS_AVG_BELOW:
                flags.append(
                    RedFlag(
                        cohort=cohort,
                        program=program,
                        days_to_start=days,
                        proj_mid=proj_mid,
                        reason=(
                            f"projected mid {proj_mid} is <{int(RED_FLAG_MID_VS_POS_AVG_BELOW*100)}% "
                            f"of position average {pos_avg} with {days}d to start"
                        ),
                    )
                )

        if days <= ZERO_WBH_NEAR_DAYS and int(row.get("wbh_count", 0)) == 0:
            flags.append(
                RedFlag(
                    cohort=cohort,
                    program=program,
                    days_to_start=days,
                    proj_mid=proj_mid,
                    reason=(
                        f"zero WBH students with {days}d to start "
                        "(escalation threshold from spec)"
                    ),
                )
            )

    return flags


def build_financial_year_view(
    cohort_df: pd.DataFrame,
    actuals_df: pd.DataFrame | None,
    start_dates: dict,
    fiscal_year: int,
    snapshot_date: str | object,
    model_confidence_note: str,
) -> dict:
    """Roll up one financial year (calendar year of each cohort's start date).

    Blends *booked actual starts* for cohorts that have already started with
    *projected starts* for cohorts still ahead. A cohort's fiscal year is the
    calendar year of its start_date, so FY2026 = cohorts 562-571 (10 UDT / 10
    NDT-Day / 5 NDT-Night). Started cohorts contribute a fixed point value
    (low = mid = high = actual_starts); future cohorts contribute their
    projection range. low <= mid <= high is preserved because each addend does.
    """
    snap = utils.parse_snapshot_date(snapshot_date)

    actual_by_code: dict[str, int] = {}
    if actuals_df is not None and len(actuals_df):
        for _, r in actuals_df.iterrows():
            try:
                actual_by_code[str(r["cohort"])] = int(r["actual_starts"])
            except (ValueError, TypeError):
                continue

    proj_by_code: dict[str, tuple[int, int, int]] = {}
    for _, r in cohort_df.iterrows():
        proj_by_code[str(r["cohort"])] = (
            int(r["proj_low"]),
            int(r["proj_mid"]),
            int(r["proj_high"]),
        )

    def _empty_program() -> dict:
        return {
            "cohort_count": 0,
            "started_count": 0,
            "actual_starts": 0,
            "proj_low": 0,
            "proj_mid": 0,
            "proj_high": 0,
        }

    per_program: dict[str, dict] = {p: _empty_program() for p in PROGRAM_ORDER}
    cohorts: list[dict] = []

    for code, sd in sorted(start_dates.items(), key=lambda kv: (kv[1], kv[0])):
        if sd.year != fiscal_year:
            continue
        program = utils.program_for_cohort(code)
        per_program.setdefault(program, _empty_program())
        started = sd < snap

        if started and code in actual_by_code:
            actual = actual_by_code[code]
            low = mid = high = actual
            status = "actual"
        elif started:
            # Past its start date but not yet booked — fall back to the last
            # projection if we still have one, else 0. Flag it as pending so the
            # dashboard can distinguish it from confirmed actuals.
            low, mid, high = proj_by_code.get(code, (0, 0, 0))
            actual = None
            status = "pending"
        elif code in proj_by_code:
            low, mid, high = proj_by_code[code]
            actual = None
            status = "projected"
        else:
            # Future cohort with no snapshot row yet (not enrolling) — no data.
            continue

        pp = per_program[program]
        pp["cohort_count"] += 1
        if started:
            pp["started_count"] += 1
            if status == "actual":
                pp["actual_starts"] += actual
        pp["proj_low"] += low
        pp["proj_mid"] += mid
        pp["proj_high"] += high

        cohorts.append(
            {
                "cohort": code,
                "program": program,
                "start_date": sd.isoformat(),
                "status": status,
                "actual_starts": actual,
                "starts_low": low,
                "starts_mid": mid,
                "starts_high": high,
            }
        )

    by_program = {p: v for p, v in per_program.items() if v["cohort_count"] > 0}
    total_low = sum(v["proj_low"] for v in by_program.values())
    total_mid = sum(v["proj_mid"] for v in by_program.values())
    total_high = sum(v["proj_high"] for v in by_program.values())
    total_actual = sum(v["actual_starts"] for v in by_program.values())

    return {
        "fiscal_year": fiscal_year,
        "label": str(fiscal_year),
        "total": {
            "actual_starts": total_actual,
            "proj_low": total_low,
            "proj_mid": total_mid,
            "proj_high": total_high,
        },
        "revenue_per_start": REVENUE_PER_START,
        "year_end_revenue_low": total_low * REVENUE_PER_START,
        "year_end_revenue_mid": total_mid * REVENUE_PER_START,
        "year_end_revenue_high": total_high * REVENUE_PER_START,
        "by_program": by_program,
        "cohorts": cohorts,
        "model_confidence_note": model_confidence_note,
    }


def build_revenue_recognition_view(
    cohort_df: pd.DataFrame,
    actuals_df: pd.DataFrame | None,
    start_dates: dict,
    snapshot_date: str | object,
    model_confidence_note: str,
) -> dict:
    """Recognize each cohort's revenue in the calendar year(s) it is earned.

    Tuition is earned pro rata over 150 attendance days (see ``recognition``), so
    a cohort that starts late in a year books part of its revenue the next year.
    Starts come from booked actuals for already-started cohorts, projections for
    the rest; revenue = starts x REVENUE_PER_START is spread across calendar
    years by attendance day. Scope = cohorts with a known start date.
    """
    snap = utils.parse_snapshot_date(snapshot_date)

    actual_by_code: dict[str, int] = {}
    if actuals_df is not None and len(actuals_df):
        for _, r in actuals_df.iterrows():
            try:
                actual_by_code[str(r["cohort"])] = int(r["actual_starts"])
            except (ValueError, TypeError):
                continue

    proj_by_code: dict[str, tuple[int, int, int]] = {}
    for _, r in cohort_df.iterrows():
        proj_by_code[str(r["cohort"])] = (
            int(r["proj_low"]),
            int(r["proj_mid"]),
            int(r["proj_high"]),
        )

    def _bucket() -> dict:
        return {
            "earned_low": 0.0,
            "earned_mid": 0.0,
            "earned_high": 0.0,
            "earned_actual": 0.0,
            "earned_projected": 0.0,
        }

    by_year: dict[int, dict] = {}
    cohorts: list[dict] = []

    for code, sd in sorted(start_dates.items(), key=lambda kv: (kv[1], kv[0])):
        program = utils.program_for_cohort(code)
        started = sd < snap

        if started and code in actual_by_code:
            low = mid = high = actual_by_code[code]
            status = "actual"
        elif started:
            low, mid, high = proj_by_code.get(code, (0, 0, 0))
            status = "pending"
        elif code in proj_by_code:
            low, mid, high = proj_by_code[code]
            status = "projected"
        else:
            continue

        spread_low = recognition.recognize(sd, low * REVENUE_PER_START)
        spread_mid = recognition.recognize(sd, mid * REVENUE_PER_START)
        spread_high = recognition.recognize(sd, high * REVENUE_PER_START)
        is_actual = status == "actual"

        for yr, amt in spread_mid.items():
            b = by_year.setdefault(yr, _bucket())
            b["earned_mid"] += amt
            b["earned_actual" if is_actual else "earned_projected"] += amt
        for yr, amt in spread_low.items():
            by_year.setdefault(yr, _bucket())["earned_low"] += amt
        for yr, amt in spread_high.items():
            by_year.setdefault(yr, _bucket())["earned_high"] += amt

        cohorts.append(
            {
                "cohort": code,
                "program": program,
                "start_date": sd.isoformat(),
                "status": status,
                "starts_mid": mid,
                "revenue_mid": mid * REVENUE_PER_START,
                "by_year": {str(y): round(a) for y, a in spread_mid.items()},
            }
        )

    years = sorted(by_year)
    by_year_out = {
        str(y): {k: round(v) for k, v in by_year[y].items()} for y in years
    }
    return {
        "years": [str(y) for y in years],
        "by_year": by_year_out,
        "cohorts": cohorts,
        "revenue_per_start": REVENUE_PER_START,
        "model_confidence_note": model_confidence_note,
    }


def build_management_view(
    cohort_df: pd.DataFrame,
    strategic: dict,
    red_flags: list[RedFlag],
    snapshot_date: str,
) -> dict:
    flag_text = (
        " · ".join(f"{f.cohort}: {f.reason}" for f in red_flags) if red_flags else "none"
    )
    fy = strategic["fiscal_year"]
    total = strategic["total"]
    booked = total["actual_starts"]
    projected_mid = total["proj_mid"] - booked
    narrative = (
        f"As of {snapshot_date}, the {fy} financial-year projection is "
        f"{total['proj_mid']} starts (range "
        f"{total['proj_low']}–{total['proj_high']}) — {booked} booked plus "
        f"{projected_mid} projected — implying "
        f"${strategic['year_end_revenue_mid']:,} in mid-case revenue. "
        f"{strategic['model_confidence_note']} "
        f"Red-flagged cohorts: {flag_text}."
    )
    return {
        "fiscal_year": fy,
        "headline_starts_mid": total["proj_mid"],
        "headline_starts_low": total["proj_low"],
        "headline_starts_high": total["proj_high"],
        "headline_actual_starts": booked,
        "headline_revenue_mid": strategic["year_end_revenue_mid"],
        "narrative": narrative,
        "red_flagged_cohorts": [asdict(f) for f in red_flags],
    }


def render_management_markdown(management: dict, snapshot_date: str) -> str:
    flags = management["red_flagged_cohorts"]
    flag_lines = (
        "\n".join(
            f"- **{f['cohort']}** ({f['days_to_start']}d to start): {f['reason']}"
            for f in flags
        )
        if flags
        else "_None._"
    )
    fy = management.get("fiscal_year", "")
    booked = management.get("headline_actual_starts", 0)
    return (
        f"# Cohort Pipeline Headline — {snapshot_date}\n\n"
        f"**FY{fy} starts (mid case):** {management['headline_starts_mid']} "
        f"(range {management['headline_starts_low']}–{management['headline_starts_high']})\n\n"
        f"**Booked to date:** {booked} starts\n\n"
        f"**Mid-case revenue:** ${management['headline_revenue_mid']:,}\n\n"
        f"## Narrative\n\n{management['narrative']}\n\n"
        f"## Red-flagged cohorts\n\n{flag_lines}\n"
    )


def build_rep_aggregate_view(rep_scorecards: list[dict]) -> dict:
    # Re-export the same shape as the rep_health payload, with a stable sort.
    sorted_reps = sorted(
        rep_scorecards,
        key=lambda r: (r.get("is_new_rep", False), -r.get("quality_score", 0)),
    )
    return {"reps": sorted_reps}
