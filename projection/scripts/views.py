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

REVENUE_PER_START = 25_300  # Per spec, blended UDT/NDT-Day/NDT-Night.

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


def build_strategic_view(
    cohort_df: pd.DataFrame,
    model_confidence_note: str,
) -> dict:
    year_low = int(cohort_df["proj_low"].sum())
    year_mid = int(cohort_df["proj_mid"].sum())
    year_high = int(cohort_df["proj_high"].sum())
    return {
        "year_end_proj_low": year_low,
        "year_end_proj_mid": year_mid,
        "year_end_proj_high": year_high,
        "revenue_per_start": REVENUE_PER_START,
        "year_end_revenue_low": year_low * REVENUE_PER_START,
        "year_end_revenue_mid": year_mid * REVENUE_PER_START,
        "year_end_revenue_high": year_high * REVENUE_PER_START,
        "by_program": {
            program: {
                "proj_low": int(group["proj_low"].sum()),
                "proj_mid": int(group["proj_mid"].sum()),
                "proj_high": int(group["proj_high"].sum()),
                "cohort_count": int(len(group)),
            }
            for program, group in cohort_df.groupby("program")
        },
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
    narrative = (
        f"As of {snapshot_date}, the mid-case year-end projection is "
        f"{strategic['year_end_proj_mid']} starts (range "
        f"{strategic['year_end_proj_low']}–{strategic['year_end_proj_high']}), "
        f"implying ${strategic['year_end_revenue_mid']:,} in mid-case revenue. "
        f"{strategic['model_confidence_note']} "
        f"Red-flagged cohorts: {flag_text}."
    )
    return {
        "headline_starts_mid": strategic["year_end_proj_mid"],
        "headline_starts_low": strategic["year_end_proj_low"],
        "headline_starts_high": strategic["year_end_proj_high"],
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
    return (
        f"# Cohort Pipeline Headline — {snapshot_date}\n\n"
        f"**Projected year-end starts (mid case):** {management['headline_starts_mid']} "
        f"(range {management['headline_starts_low']}–{management['headline_starts_high']})\n\n"
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
