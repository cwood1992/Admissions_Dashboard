"""Guided CLI to record actuals for a completed cohort.

Usage:
    uv run python -m scripts.record_actuals UDT566
    uv run python -m scripts.record_actuals UDT566 --no-calibrate
    uv run python -m scripts.record_actuals UDT566 --at-start-date 2026-05-15

Workflow:
1. Look up the cohort's start_date and program.
2. Find the closest snapshot CSV <= start_date and pre-fill tier counts
   (wbh_at_start, vip_at_start, priority_at_start) from it.
3. Try to find historical snapshots at start_date - 60/30/14/7 days for the
   retrospective projection values; pre-fill proj_at_*d when available.
4. Prompt for actual_starts and per-tier started counts.
5. Append a row to completed/cohort_actuals.csv (calibrated_at blank).
6. Offer to run calibrate.py immediately.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from scripts import calibrate as calibrate_mod
from scripts import high_water, ingest, utils

PROJECTION_INTERVALS = [60, 30, 14, 7]  # days before start


def derive_from_booked_ccs(cohort: str, ccs_path: Path) -> dict:
    """Auto-derive a cohort_actuals row from a booked-class CCS export.

    Ground truth: total_ever_enrolled = row count (after dropping REENROLLs);
    actual_starts = rows whose CCS Status == utils.ENROLLMENT_STATUS_ACTIVE
    (started in THIS cohort, NEW or TRANSFER-IN); tier counts cross-tab Action
    Status against started. REENROLL rows are excluded entirely — they're
    previously-dropped students returning, not fresh pipeline starts.
    """
    df = utils.load_ccs_csv(ccs_path)
    program = utils.program_for_cohort(cohort)

    enroll_type = (
        df[utils.CCS_COLUMNS["enrollment_type"]].astype("string").fillna("").str.strip().str.upper()
    )
    df = df[enroll_type != utils.ENROLLMENT_TYPE_REENROLL].reset_index(drop=True)
    n = len(df)

    ccs_status = (
        df[utils.CCS_COLUMNS["enrollment_status"]].astype("string").fillna("").str.strip()
    )
    started = ccs_status == utils.ENROLLMENT_STATUS_ACTIVE
    flags = ingest._parse_action_flags(df) if n else None

    def tier_counts(flag_col: str) -> tuple[int, int]:
        if flags is None:
            return 0, 0
        at_start = int(flags[flag_col].sum())
        that_started = int((flags[flag_col] & started).sum())
        return at_start, that_started

    wbh_at, wbh_started = tier_counts("wbh")
    vip_at, vip_started = tier_counts("vip")
    if flags is None:
        prio_at = prio_started = 0
    else:
        any_prio = flags[["p_fa", "p_va", "p_acc", "p_adm"]].any(axis=1)
        prio_at = int(any_prio.sum())
        prio_started = int((any_prio & started).sum())

    return {
        "cohort": cohort,
        "program": program,
        "actual_starts": int(started.sum()),
        "total_ever_enrolled": n,
        "wbh_at_start": wbh_at,
        "wbh_that_started": wbh_started,
        "vip_at_start": vip_at,
        "vip_that_started": vip_started,
        "priority_at_start": prio_at,
        "priority_that_started": prio_started,
        "proj_at_60d": "",
        "proj_at_30d": "",
        "proj_at_14d": "",
        "proj_at_7d": "",
        "calibrated_at": "",
    }


def _list_snapshots() -> list[tuple[date, Path]]:
    return utils.list_snapshots()


def _find_snapshot_on_or_before(target: date) -> tuple[date, Path] | None:
    candidates = [(d, p) for d, p in _list_snapshots() if d <= target]
    return max(candidates, default=None)


def _find_snapshot_closest_to(target: date, tolerance_days: int = 3) -> tuple[date, Path] | None:
    candidates = [
        (abs((d - target).days), d, p) for d, p in _list_snapshots()
    ]
    candidates.sort()
    if not candidates:
        return None
    diff, d, p = candidates[0]
    if diff > tolerance_days:
        return None
    return d, p


def _row_for_cohort(snapshot_path: Path, cohort: str) -> pd.Series | None:
    df = pd.read_csv(snapshot_path)
    rows = df[df["cohort"] == cohort]
    return rows.iloc[0] if len(rows) else None


def _ask(prompt: str, default: str | int | None = None, type_=str):
    suffix = f" [{default}]" if default is not None and default != "" else ""
    raw = input(f"  {prompt}{suffix}: ").strip()
    if raw == "":
        if default is None or default == "":
            return default
        raw = str(default)
    try:
        return type_(raw)
    except (ValueError, TypeError):
        print(f"    invalid value, keeping default")
        return default


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    raw = input(f"  {prompt}{suffix}: ").strip().lower()
    if raw == "":
        return default
    return raw in ("y", "yes")


def record_actuals_interactive(cohort: str, at_start_date_override: date | None = None) -> dict:
    start_dates = ingest.load_program_start_dates()
    if cohort not in start_dates:
        print(f"ERROR: cohort {cohort!r} not in program_start_dates_2026.csv.")
        print("Add it there first.")
        sys.exit(2)
    start_date = start_dates[cohort]
    program = utils.program_for_cohort(cohort)

    print()
    print(f"Recording actuals for {cohort} ({program}, started {start_date}).")
    print()

    # Locate the at-start snapshot.
    target = at_start_date_override or start_date
    found = _find_snapshot_on_or_before(target)
    if found is None:
        print(f"  No snapshot found on or before {target}. Tier counts will need manual entry.")
        pre_row = None
        used_snapshot_date = None
    else:
        used_snapshot_date, snapshot_path = found
        pre_row = _row_for_cohort(snapshot_path, cohort)
        if pre_row is None:
            print(f"  Snapshot {used_snapshot_date} exists but has no row for {cohort}.")
        else:
            days_before = (start_date - used_snapshot_date).days
            print(
                f"  Pre-fill basis: {used_snapshot_date} snapshot "
                f"({days_before}d before start)"
            )

    def pre(field: str) -> int:
        if pre_row is None:
            return 0
        try:
            return int(pre_row[field])
        except (KeyError, ValueError, TypeError):
            return 0

    priority_at_start_default = (
        pre("p_fa_count") + pre("p_va_count") + pre("p_acc_count") + pre("p_adm_count")
    )

    print()
    print("Tier counts at start (pre-filled from snapshot; press Enter to accept):")
    wbh_at_start = _ask("wbh_at_start", default=pre("wbh_count"), type_=int)
    vip_at_start = _ask("vip_at_start", default=pre("vip_count"), type_=int)
    priority_at_start = _ask("priority_at_start", default=priority_at_start_default, type_=int)

    print()
    print("Actual outcomes:")
    actual_starts = _ask("actual_starts (total)", type_=int)
    if actual_starts is None:
        print("ERROR: actual_starts is required.")
        sys.exit(2)
    total_ever_enrolled = _ask(
        "total_ever_enrolled (final count from CCS)",
        default=pre("total_ever_enrolled") or "",
        type_=int,
    )
    wbh_that_started = _ask("wbh_that_started", default=min(wbh_at_start, actual_starts), type_=int)
    vip_that_started = _ask("vip_that_started", default=0, type_=int)
    priority_that_started = _ask("priority_that_started", default=0, type_=int)

    # Optional retrospective projections.
    print()
    print("Retrospective projections at 60/30/14/7d before start (Enter to skip):")
    proj_values: dict[str, int | str] = {}
    for days_before in PROJECTION_INTERVALS:
        target_date = start_date - timedelta(days=days_before)
        snap = _find_snapshot_closest_to(target_date)
        default_proj: int | str = ""
        if snap:
            d, p = snap
            row = _row_for_cohort(p, cohort)
            if row is not None and "proj_mid" in row and pd.notna(row["proj_mid"]):
                default_proj = int(row["proj_mid"])
        v = _ask(f"proj_at_{days_before}d", default=default_proj, type_=int)
        proj_values[f"proj_at_{days_before}d"] = v if v is not None else ""

    row = {
        "cohort": cohort,
        "program": program,
        "actual_starts": actual_starts,
        "total_ever_enrolled": total_ever_enrolled or "",
        "wbh_at_start": wbh_at_start,
        "wbh_that_started": wbh_that_started,
        "vip_at_start": vip_at_start,
        "vip_that_started": vip_that_started,
        "priority_at_start": priority_at_start,
        "priority_that_started": priority_that_started,
        **proj_values,
        "calibrated_at": "",
    }
    return row


def append_row(row: dict, path: Path | None = None) -> Path:
    path = path or utils.COMPLETED_DIR / "cohort_actuals.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        existing = pd.read_csv(path)
        # If cohort already recorded, warn but allow append (calibrate would dedupe later).
        if (existing["cohort"] == row["cohort"]).any():
            print(
                f"  WARN: {row['cohort']} already in {path.name}. Appending duplicate row;"
                " calibrate.py will treat unrecorded rows as pending."
            )
        new_df = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        new_df = pd.DataFrame([row])
    new_df.to_csv(path, index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Guided CLI to record cohort actuals.")
    parser.add_argument("cohort", help="Cohort code, e.g. UDT566.")
    parser.add_argument(
        "--at-start-date",
        default=None,
        help="Override the snapshot date used as 'at start' basis (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--from-ccs",
        default=None,
        help="Path to a booked-class CCS export; auto-derive actuals from it "
        "instead of prompting.",
    )
    parser.add_argument(
        "--no-calibrate",
        action="store_true",
        help="Append the row but don't run calibrate.py at the end.",
    )
    args = parser.parse_args()

    if args.from_ccs:
        row = derive_from_booked_ccs(args.cohort, Path(args.from_ccs))
        print(f"Derived from {args.from_ccs}:")
        for k, v in row.items():
            if k not in ("cohort", "program", "calibrated_at") and not str(k).startswith("proj_"):
                print(f"  {k}: {v}")
        if not _confirm("Accept these and append?"):
            print("Aborted.")
            return
    else:
        at_start = (
            utils.parse_snapshot_date(args.at_start_date) if args.at_start_date else None
        )
        row = record_actuals_interactive(args.cohort, at_start)
    path = append_row(row)
    # Booked CCS is ground truth — supersede the high-water proxy for this cohort.
    try:
        high_water.mark_superseded(row["cohort"], int(row["total_ever_enrolled"]))
    except (ValueError, TypeError):
        pass
    print()
    print(f"Appended {row['cohort']} to {path}.")

    if args.no_calibrate:
        print("Skipping calibrate (--no-calibrate). Run it later with:")
        print("  uv run python -m scripts.calibrate")
        return

    print()
    if _confirm("Run calibration now?"):
        actuals = pd.read_csv(path)
        ate_df = pd.read_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv").set_index("program")
        tier_df = pd.read_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv").set_index("tier")
        curves_df = pd.read_csv(utils.BASELINES_DIR / "accumulation_curves.csv")
        new_ate, new_tier, new_curves, result = calibrate_mod.calibrate(
            actuals, ate_df, tier_df, curves_df=curves_df
        )
        new_ate.to_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv")
        new_tier.to_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv")
        if new_curves is not None:
            new_curves.to_csv(utils.BASELINES_DIR / "accumulation_curves.csv", index=False)
        actuals["calibrated_at"] = actuals["calibrated_at"].astype("object")
        pending = actuals["calibrated_at"].isna() | (actuals["calibrated_at"] == "")
        actuals.loc[pending, "calibrated_at"] = date.today().isoformat()
        actuals.to_csv(path, index=False)
        calibrate_mod.write_calibration_log(
            utils.PROJECT_ROOT / "calibration_log.md", result
        )
        print()
        print(f"Calibrated {len(result.cohorts_processed)} cohort(s). Baseline deltas:")
        for d in result.baseline_deltas:
            print(f"  - {d}")
        if result.escalation_flag:
            print()
            print(f"  ESCALATION: {result.escalation_reason}")


if __name__ == "__main__":
    main()
