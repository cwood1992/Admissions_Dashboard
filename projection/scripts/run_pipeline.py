"""Run the full pipeline for a snapshot date end-to-end.

ingest -> projections -> dashboard export.
Reads raw/<date>/ and produces snapshot CSVs, projected CSV, and dashboard JSON.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import (
    export_dashboard_data,
    high_water,
    ingest,
    projections,
    rep_health,
    utils,
    velocity,
    views,
)


_SNAPSHOT_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_snapshot\.csv$")


def find_most_recent_prior_date(reference_date: date) -> str | None:
    """Scan snapshots/ for the most recent snapshot CSV strictly before reference_date."""
    if not utils.SNAPSHOTS_DIR.exists():
        return None
    candidates: list[date] = []
    for p in utils.SNAPSHOTS_DIR.glob("*_snapshot.csv"):
        m = _SNAPSHOT_DATE_RE.match(p.name)
        if not m:
            continue
        try:
            d = utils.parse_snapshot_date(m.group(1))
        except ValueError:
            continue
        if d < reference_date:
            candidates.append(d)
    if not candidates:
        return None
    return max(candidates).isoformat()


def find_most_recent_raw_date() -> str | None:
    """Find the most recent raw/<date>/ folder by name, if any."""
    if not utils.RAW_DIR.exists():
        return None
    candidates: list[date] = []
    for p in utils.RAW_DIR.iterdir():
        if not p.is_dir():
            continue
        try:
            d = utils.parse_snapshot_date(p.name)
        except ValueError:
            continue
        candidates.append(d)
    return max(candidates).isoformat() if candidates else None


def run(
    snapshot_date: str,
    raw_dir: Path | None = None,
    strict: bool = True,
    prior_date: str | None = None,
) -> dict:
    raw_dir = raw_dir or utils.snapshot_dir_for(snapshot_date)

    cohort_df, rep_df = ingest.ingest_snapshot_dir(snapshot_date, raw_dir, strict=strict)

    # Roll the per-cohort enrollment high-water mark and attach it.
    hw = high_water.update_high_water(cohort_df, str(snapshot_date))
    cohort_df = high_water.annotate_cohort_df(cohort_df, hw)

    enriched = projections.project_dataframe(cohort_df)

    has_snapshot_velocity = (
        "weekly_velocity" in enriched.columns
        and enriched["weekly_velocity"].notna().any()
    )
    if has_snapshot_velocity:
        # EnrollList path: velocity derives from Current Enroll Date at ingest;
        # no prior snapshot needed.
        curve = velocity.load_accumulation_curves()
        pos = projections.load_position_averages()
        enriched = velocity.classify_velocity_from_snapshot(enriched, curve, pos)
    elif prior_date:
        # Legacy week-over-week path (old per-cohort CCS format).
        prior_path = utils.SNAPSHOTS_DIR / f"{prior_date}_snapshot.csv"
        if prior_path.exists():
            prior_df = pd.read_csv(prior_path)
            curve = velocity.load_accumulation_curves()
            pos = projections.load_position_averages()
            gap_days = (
                utils.parse_snapshot_date(snapshot_date)
                - utils.parse_snapshot_date(prior_date)
            ).days
            enriched = velocity.compute_velocity(
                enriched, prior_df, curve, pos, snapshot_gap_days=gap_days
            )

    cohort_path, rep_path = ingest.write_snapshot_files(enriched, rep_df, snapshot_date)
    dashboard_json = export_dashboard_data.export(cohort_path, rep_path)

    # Rep health scorecards across all cohorts in this snapshot.
    cards = rep_health.build_scorecards_from_raw(snapshot_date, raw_dir)
    rep_health_path = utils.DASHBOARD_DATA_DIR / "rep_health.json"
    rep_health_path.parent.mkdir(parents=True, exist_ok=True)
    rep_payload = {
        "snapshot_date": str(snapshot_date),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "reps": rep_health.scorecards_to_dicts(cards),
    }
    rep_health_path.write_text(json.dumps(rep_payload, indent=2), encoding="utf-8")
    rep_health_path.with_suffix(".js").write_text(
        f"window.REP_HEALTH = {json.dumps(rep_payload, indent=2)};\n",
        encoding="utf-8",
    )

    # Strategic + management views.
    tiers = projections.load_confidence_tier_rates()
    pos = projections.load_position_averages()
    confidence_note = (
        "Model is data-starved: 0 completed cohorts feed calibration yet. "
        "Position averages and confidence tier rates are placeholders."
        if tiers.is_placeholder
        else "Model has calibrated confidence tier rates."
    )
    strategic = views.build_strategic_view(enriched, confidence_note)
    red_flags = views.compute_red_flags(enriched, pos)
    management = views.build_management_view(enriched, strategic, red_flags, str(snapshot_date))

    views_payload = {
        "snapshot_date": str(snapshot_date),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "strategic": strategic,
        "management": management,
    }
    views_path = utils.DASHBOARD_DATA_DIR / "views.json"
    views_path.write_text(json.dumps(views_payload, indent=2), encoding="utf-8")
    views_path.with_suffix(".js").write_text(
        f"window.VIEWS = {json.dumps(views_payload, indent=2)};\n",
        encoding="utf-8",
    )

    # Markdown export of management view for email / vault distribution.
    md_path = utils.PROJECT_ROOT / "snapshots" / f"{snapshot_date}_management.md"
    md_path.write_text(
        views.render_management_markdown(management, str(snapshot_date)),
        encoding="utf-8",
    )

    return {
        "cohort_csv": cohort_path,
        "rep_csv": rep_path,
        "dashboard_json": dashboard_json,
        "rep_health_json": rep_health_path,
        "views_json": views_path,
        "management_md": md_path,
        "rows": len(enriched),
        "rep_scorecards": len(cards),
        "red_flags": len(red_flags),
        "velocity": bool(prior_date),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ingest -> projections -> velocity -> dashboard."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date (YYYY-MM-DD). Defaults to most recent raw/<date>/ folder, else today.",
    )
    parser.add_argument(
        "--prior-date",
        default=None,
        help=(
            "Prior snapshot date for velocity (YYYY-MM-DD). If omitted, the most "
            "recent snapshot CSV strictly before --date is used. Pass '--prior-date none' "
            "to explicitly disable velocity (e.g. the very first run)."
        ),
    )
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    snapshot_date = args.date or find_most_recent_raw_date() or date.today().isoformat()
    if args.prior_date is None:
        prior_date = find_most_recent_prior_date(utils.parse_snapshot_date(snapshot_date))
        if prior_date:
            print(f"Auto-detected prior snapshot: {prior_date}")
        else:
            print("No prior snapshot found; velocity will be skipped.")
    elif args.prior_date.lower() == "none":
        prior_date = None
    else:
        prior_date = args.prior_date

    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    print(f"Running pipeline for snapshot date: {snapshot_date}")
    result = run(snapshot_date, raw_dir, strict=not args.no_strict, prior_date=prior_date)
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
