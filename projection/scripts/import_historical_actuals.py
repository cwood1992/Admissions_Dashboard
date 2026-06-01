"""One-shot importer for historical cohort actuals (2022-2026).

Reads `summary_YYYY.csv` files (per-rep granularity) from a source directory
and produces:

- `completed/cohort_actuals.csv` — aggregated per cohort, in the schema
  `scripts/calibrate.py` consumes. Marked `calibrated_at` immediately so the
  weekly per-observation blend doesn't reprocess them.
- `completed/cohort_actuals_by_rep.csv` — per-rep detail preserved for future
  use (rep-level historical baselines, durability calibration, etc.).
- `baselines/ate_conversion_rates.csv` — empirical low/mid/high per program
  computed directly from the bulk data (NOT through the per-observation blend,
  which would anchor too heavily on the prior).
- `calibration_log.md` — bulk-import entry.

Tier rate calibration is *not* done here: the historical data has no
WBH/VIP/Priority breakdown.

Run once. Subsequent newly-completed cohorts use `calibrate.py` per the normal
weekly cycle.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import utils
from scripts.calibrate import write_calibration_log, CalibrationResult

# Source program labels -> pipeline program labels.
PROGRAM_LABEL_MAP = {
    "UDT": "UDT",
    "NDT": "NDT-Day",
    "NDT-NC": "NDT-Night",
}

# Quantile bounds for empirical low/high. p25/p75 captures the middle 50% of
# observed cohort outcomes — a defensible "uncertainty band" without being
# distorted by outlier cohorts.
LOW_QUANTILE = 0.25
HIGH_QUANTILE = 0.75


def load_per_rep_summaries(source_dir: Path) -> pd.DataFrame:
    paths = sorted(source_dir.glob("summary_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No summary_*.csv files in {source_dir}")
    frames = [pd.read_csv(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    # Translate program label to pipeline vocabulary.
    df["program_label"] = df["Program"].map(PROGRAM_LABEL_MAP)
    if df["program_label"].isna().any():
        unknown = df.loc[df["program_label"].isna(), "Program"].unique()
        raise ValueError(f"Unknown program labels in source: {list(unknown)}")
    return df


def aggregate_to_cohort(per_rep: pd.DataFrame) -> pd.DataFrame:
    grouped = per_rep.groupby(["Year", "Cohort", "program_label"], as_index=False).agg(
        total_ever_enrolled=("Enrollments", "sum"),
        actual_starts=("Starts", "sum"),
        new_count=("New", "sum"),
        transfer_count=("Transfer", "sum"),
        reenroll_count=("Reenroll", "sum"),
    )
    grouped["ate_to_start"] = grouped["actual_starts"] / grouped["total_ever_enrolled"]
    return grouped.sort_values(["Year", "Cohort"]).reset_index(drop=True)


def compute_empirical_ate_rates(cohort_agg: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for program, group in cohort_agg.groupby("program_label"):
        rates = group["ate_to_start"].replace([np.inf, -np.inf], np.nan).dropna()
        rates = rates[(rates >= 0) & (rates <= 1)]
        if rates.empty:
            continue
        rows.append(
            {
                "program": program,
                "low": round(float(rates.quantile(LOW_QUANTILE)), 4),
                "mid": round(float(rates.mean()), 4),
                "high": round(float(rates.quantile(HIGH_QUANTILE)), 4),
                "n_cohorts": int(len(rates)),
                "min": round(float(rates.min()), 4),
                "max": round(float(rates.max()), 4),
                "stddev": round(float(rates.std(ddof=1)) if len(rates) > 1 else 0.0, 4),
            }
        )
    return pd.DataFrame(rows)


def to_actuals_schema(cohort_agg: pd.DataFrame, calibrated_date: date) -> pd.DataFrame:
    """Reshape the cohort-aggregate frame into the calibrate.py schema."""
    out = pd.DataFrame(
        {
            "cohort": cohort_agg["Cohort"],
            "program": cohort_agg["program_label"],
            "actual_starts": cohort_agg["actual_starts"],
            "total_ever_enrolled": cohort_agg["total_ever_enrolled"],
            "wbh_at_start": "",
            "wbh_that_started": "",
            "vip_at_start": "",
            "vip_that_started": "",
            "priority_at_start": "",
            "priority_that_started": "",
            "proj_at_60d": "",
            "proj_at_30d": "",
            "proj_at_14d": "",
            "proj_at_7d": "",
            "calibrated_at": calibrated_date.isoformat(),
        }
    )
    return out


def write_ate_baseline(empirical: pd.DataFrame, out_path: Path) -> None:
    rows = []
    for _, row in empirical.iterrows():
        rows.append(
            {
                "program": row["program"],
                "low": row["low"],
                "mid": row["mid"],
                "high": row["high"],
                "source": f"empirical-2022-2026-n{row['n_cohorts']}",
                "notes": (
                    f"p25/mean/p75 across {row['n_cohorts']} completed cohorts. "
                    f"min={row['min']}, max={row['max']}, stddev={row['stddev']}"
                ),
            }
        )
    pd.DataFrame(rows).to_csv(out_path, index=False)


def build_log_result(
    cohort_agg: pd.DataFrame, empirical: pd.DataFrame
) -> CalibrationResult:
    accuracy_lines = []
    for program, group in cohort_agg.groupby("program_label"):
        accuracy_lines.append(
            f"- {program}: {len(group)} cohorts, "
            f"empirical ate-to-start mean = {group['ate_to_start'].mean():.4f}"
        )
    deltas = [
        f"{r['program']} ate range: [{r['low']}, {r['mid']}, {r['high']}] "
        f"from n={r['n_cohorts']} cohorts (replaced placeholder)"
        for _, r in empirical.iterrows()
    ]
    return CalibrationResult(
        cohorts_processed=list(cohort_agg["Cohort"]),
        baseline_deltas=deltas,
        accuracy_lines=accuracy_lines,
        escalation_flag=False,
        escalation_reason="",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-import historical completed cohort actuals."
    )
    parser.add_argument(
        "--source",
        default=str(
            Path("D:/Projects/Programming/admissions_dashboard_v2/admissions_dashboard")
        ),
        help="Directory containing summary_YYYY.csv files.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source)
    per_rep = load_per_rep_summaries(source_dir)
    cohort_agg = aggregate_to_cohort(per_rep)
    empirical = compute_empirical_ate_rates(cohort_agg)

    print(f"Aggregated {len(cohort_agg)} cohorts from {per_rep['Year'].nunique()} years")
    print()
    print("Empirical ate-to-start by program:")
    print(empirical.to_string(index=False))
    print()
    if args.dry_run:
        print("Dry run — no files written.")
        return

    today = date.today()
    actuals_df = to_actuals_schema(cohort_agg, today)
    actuals_path = utils.COMPLETED_DIR / "cohort_actuals.csv"
    actuals_df.to_csv(actuals_path, index=False)
    print(f"Wrote {len(actuals_df)} cohorts -> {actuals_path}")

    by_rep_path = utils.COMPLETED_DIR / "cohort_actuals_by_rep.csv"
    per_rep_out = per_rep.rename(
        columns={
            "Year": "year",
            "Cohort": "cohort",
            "program_label": "program",
            "Rep": "rep",
            "Enrollments": "enrollments",
            "Starts": "starts",
            "StartRate": "start_rate_pct",
            "New": "new_enrolled",
            "Transfer": "transfer_enrolled",
            "Reenroll": "reenroll_enrolled",
        }
    )[
        [
            "year",
            "cohort",
            "program",
            "rep",
            "enrollments",
            "starts",
            "start_rate_pct",
            "new_enrolled",
            "transfer_enrolled",
            "reenroll_enrolled",
        ]
    ]
    per_rep_out.to_csv(by_rep_path, index=False)
    print(f"Wrote {len(per_rep_out)} (cohort,rep) rows -> {by_rep_path}")

    ate_path = utils.BASELINES_DIR / "ate_conversion_rates.csv"
    write_ate_baseline(empirical, ate_path)
    print(f"Replaced empirical ate baseline -> {ate_path}")

    log_path = utils.PROJECT_ROOT / "calibration_log.md"
    result = build_log_result(cohort_agg, empirical)
    write_calibration_log(log_path, result, run_date=today)
    print(f"Appended import entry to {log_path}")


if __name__ == "__main__":
    main()
