from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts import utils


def build_snapshot_payload(cohort_df: pd.DataFrame, rep_df: pd.DataFrame) -> dict:
    cohorts = cohort_df.to_dict(orient="records")
    reps_by_cohort: dict[str, list[dict]] = {}
    if not rep_df.empty:
        for cohort, group in rep_df.groupby("cohort"):
            reps_by_cohort[cohort] = group.to_dict(orient="records")
    snapshot_date = (
        cohort_df["snapshot_date"].iloc[0] if not cohort_df.empty else None
    )
    return {
        "snapshot_date": snapshot_date,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "cohorts": cohorts,
        "reps_by_cohort": reps_by_cohort,
    }


def export(
    snapshot_csv: Path,
    rep_csv: Path,
    out_path: Path | None = None,
) -> Path:
    out_path = out_path or utils.DASHBOARD_DATA_DIR / "snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cohort_df = pd.read_csv(snapshot_csv)
    rep_df = pd.read_csv(rep_csv) if rep_csv.exists() else pd.DataFrame()
    payload = build_snapshot_payload(cohort_df, rep_df)
    json_text = json.dumps(payload, indent=2, default=str)
    out_path.write_text(json_text, encoding="utf-8")
    # Sidecar JS file so the dashboard can load over file:// without CORS issues.
    js_path = out_path.with_suffix(".js")
    js_path.write_text(f"window.SNAPSHOT_DATA = {json_text};\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export projected snapshot to dashboard JSON.")
    parser.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument(
        "--snapshot-csv",
        default=None,
        help="Snapshot CSV path (defaults to snapshots/<date>_snapshot.csv).",
    )
    parser.add_argument(
        "--rep-csv",
        default=None,
        help="Rep CSV path (defaults to snapshots/<date>_reps.csv).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output JSON path (defaults to dashboard/data/snapshot.json).",
    )
    args = parser.parse_args()

    snap = (
        Path(args.snapshot_csv)
        if args.snapshot_csv
        else utils.SNAPSHOTS_DIR / f"{args.date}_snapshot.csv"
    )
    reps = (
        Path(args.rep_csv)
        if args.rep_csv
        else utils.SNAPSHOTS_DIR / f"{args.date}_reps.csv"
    )
    out = Path(args.out) if args.out else None
    result = export(snap, reps, out)
    print(f"Wrote dashboard JSON to {result}")


if __name__ == "__main__":
    main()
