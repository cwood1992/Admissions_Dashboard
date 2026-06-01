"""List cohorts past their start_date that don't yet have actuals recorded.

Run weekly to keep the calibration feedback loop honest — anything that's been
sitting in 'pending' for too long means the model isn't learning from it.

Usage:
    uv run python -m scripts.pending_calibrations [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from scripts import ingest, utils


def find_pending(as_of: date) -> list[dict]:
    start_dates = ingest.load_program_start_dates()
    actuals_path = utils.COMPLETED_DIR / "cohort_actuals.csv"
    if actuals_path.exists():
        try:
            recorded = set(pd.read_csv(actuals_path)["cohort"].astype(str))
        except (pd.errors.EmptyDataError, KeyError):
            recorded = set()
    else:
        recorded = set()

    pending = []
    for cohort, start_date in start_dates.items():
        if start_date > as_of:
            continue
        if cohort in recorded:
            continue
        days_since_start = (as_of - start_date).days
        pending.append(
            {"cohort": cohort, "start_date": start_date, "days_since_start": days_since_start}
        )
    pending.sort(key=lambda r: r["start_date"])
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(description="List cohorts overdue for actuals entry.")
    parser.add_argument(
        "--as-of",
        default=None,
        help="Reference date (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()
    as_of = utils.parse_snapshot_date(args.as_of) if args.as_of else date.today()

    pending = find_pending(as_of)
    if not pending:
        print(f"No pending calibrations as of {as_of}. Feedback loop is up to date.")
        return

    print(f"{len(pending)} cohort(s) past start_date with no actuals recorded (as of {as_of}):")
    print()
    print(f"  {'Cohort':12} {'Started':12} {'Days since':>11}")
    for row in pending:
        print(
            f"  {row['cohort']:12} {row['start_date'].isoformat():12} {row['days_since_start']:>11}"
        )
    print()
    print(
        "When the actual starts are known, append a row to completed/cohort_actuals.csv "
        "and run: uv run python -m scripts.calibrate"
    )


if __name__ == "__main__":
    main()
