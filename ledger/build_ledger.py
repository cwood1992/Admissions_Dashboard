#!/usr/bin/env python3
"""Build the canonical cohort ledger — the data foundation for cash management.

Joins the two engines' OUTPUTS (never their internals) by cohort code into one
record-per-cohort ledger spanning the full lifecycle:

    completed  cohorts -> actual starts        (projection/completed/cohort_actuals.csv)
    in-flight  cohorts -> enrolled + projected (projection/dashboard/data/snapshot.json)

Total pipeline cash = booked revenue (actual starts) + projected revenue
(in-flight, mid case), at REVENUE_PER_START each.

This is Phase 1: it reads outputs only and changes no pipeline. For completed
cohorts it also cross-checks the historical dashboard's summary (summary_*.csv)
and records `reconciliation_warnings` wherever the Active-only actuals disagree
with the summary's Active+Drop+Grad starts — surfacing the starts-definition
fork that the later ingestion-dedup step resolves.

Run from the repo root:  python ledger/build_ledger.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROJECTION = ROOT / "projection"

# Reuse the projection engine's canonical helpers — single source of truth for
# program labels, year-cycle position, and the blended revenue figure.
sys.path.insert(0, str(PROJECTION))
from scripts.utils import position_for_cohort, program_for_cohort  # noqa: E402
from scripts.views import REVENUE_PER_START  # noqa: E402

ACTUALS_CSV = PROJECTION / "completed" / "cohort_actuals.csv"
SNAPSHOT_JSON = PROJECTION / "dashboard" / "data" / "snapshot.json"
START_DATES_CSV = PROJECTION / "baselines" / "program_start_dates_2026.csv"
SUMMARY_INDEX = ROOT / "summary_index.json"
OUT_JSON = ROOT / "ledger" / "cohort_ledger.json"


def _int(value) -> int | None:
    """Coerce to int, treating NaN / blank / None as missing."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    return int(float(s))


def load_start_dates() -> dict[int, str]:
    """cohort_number -> ISO start date, from the projection baseline."""
    if not START_DATES_CSV.exists():
        return {}
    df = pd.read_csv(START_DATES_CSV, dtype=str, keep_default_na=False)
    out: dict[int, str] = {}
    for _, row in df.iterrows():
        num = _int(row.get("cohort_number"))
        raw = str(row.get("start_date", "")).strip()
        if num is None or not raw:
            continue
        try:
            out[num] = datetime.strptime(raw, "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
    return out


def cohort_number(cohort: str) -> int | None:
    digits = "".join(c for c in cohort if c.isdigit())
    return int(digits) if digits else None


def load_summary_starts() -> dict[str, int]:
    """Cohort code -> total Starts from the historical summary (sum across reps
    and years; cohort numbers are globally unique so codes don't collide)."""
    if not SUMMARY_INDEX.exists():
        return {}
    index = json.loads(SUMMARY_INDEX.read_text(encoding="utf-8"))
    starts: dict[str, int] = {}
    for entry in index.get("files", []):
        path = ROOT / entry["file"]
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if "Cohort" not in df.columns or "Starts" not in df.columns:
            continue
        grouped = df.groupby("Cohort")["Starts"].sum()
        for cohort, total in grouped.items():
            starts[str(cohort).strip().upper()] = starts.get(str(cohort).strip().upper(), 0) + int(total)
    return starts


def load_completed() -> list[dict]:
    if not ACTUALS_CSV.exists():
        return []
    df = pd.read_csv(ACTUALS_CSV, dtype=str, keep_default_na=False)
    rows = []
    for _, r in df.iterrows():
        cohort = str(r["cohort"]).strip().upper()
        if not cohort:
            continue
        rows.append(
            {
                "cohort": cohort,
                "actual_starts": _int(r.get("actual_starts")),
                "total_ever_enrolled": _int(r.get("total_ever_enrolled")),
            }
        )
    return rows


def load_snapshot() -> tuple[str | None, list[dict]]:
    if not SNAPSHOT_JSON.exists():
        return None, []
    data = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))
    rows = []
    for c in data.get("cohorts", []):
        cohort = str(c.get("cohort", "")).strip().upper()
        if not cohort:
            continue
        rows.append(
            {
                "cohort": cohort,
                "start_date": c.get("start_date"),
                "currently_enrolled": _int(c.get("currently_enrolled")),
                "proj_low": _int(c.get("proj_low")),
                "proj_mid": _int(c.get("proj_mid")),
                "proj_high": _int(c.get("proj_high")),
            }
        )
    return data.get("snapshot_date"), rows


def build() -> dict:
    start_dates = load_start_dates()
    summary_starts = load_summary_starts()
    completed = load_completed()
    snapshot_date, in_flight = load_snapshot()

    completed_codes = {r["cohort"] for r in completed}
    ledger: dict[str, dict] = {}
    warnings: list[dict] = []

    def base_record(cohort: str) -> dict:
        return {
            "cohort": cohort,
            "program": program_for_cohort(cohort),
            "position_in_year": position_for_cohort(cohort),
            "start_date": start_dates.get(cohort_number(cohort)),
            "lifecycle": None,
            "actual_starts": None,
            "total_ever_enrolled": None,
            "currently_enrolled": None,
            "proj_low": None,
            "proj_mid": None,
            "proj_high": None,
            "booked_revenue": None,
            "projected_revenue_mid": None,
            "reconciliation": None,
        }

    # In-flight first; completed takes precedence if a cohort appears in both.
    for r in in_flight:
        if r["cohort"] in completed_codes:
            continue
        rec = base_record(r["cohort"])
        rec["lifecycle"] = "in_flight"
        if r.get("start_date"):
            rec["start_date"] = r["start_date"]
        rec["currently_enrolled"] = r["currently_enrolled"]
        rec["proj_low"] = r["proj_low"]
        rec["proj_mid"] = r["proj_mid"]
        rec["proj_high"] = r["proj_high"]
        if rec["proj_mid"] is not None:
            rec["projected_revenue_mid"] = rec["proj_mid"] * REVENUE_PER_START
        ledger[r["cohort"]] = rec

    for r in completed:
        rec = base_record(r["cohort"])
        rec["lifecycle"] = "completed"
        rec["actual_starts"] = r["actual_starts"]
        rec["total_ever_enrolled"] = r["total_ever_enrolled"]
        if rec["actual_starts"] is not None:
            rec["booked_revenue"] = rec["actual_starts"] * REVENUE_PER_START
        v2 = summary_starts.get(r["cohort"])
        if v2 is not None and rec["actual_starts"] is not None:
            matches = v2 == rec["actual_starts"]
            rec["reconciliation"] = {"v2_starts": v2, "matches": matches}
            if not matches:
                warnings.append(
                    {
                        "cohort": r["cohort"],
                        "actual_starts": rec["actual_starts"],
                        "v2_starts": v2,
                        "note": (
                            "historical summary counts Active+Drop+Grad; projection "
                            "actuals count Active only — resolve in ingestion dedup"
                        ),
                    }
                )
        ledger[r["cohort"]] = rec

    cohorts = sorted(
        ledger.values(),
        key=lambda r: (cohort_number(r["cohort"]) or 0, r["program"]),
    )

    booked_starts = sum(r["actual_starts"] or 0 for r in cohorts if r["lifecycle"] == "completed")
    booked_revenue = sum(r["booked_revenue"] or 0 for r in cohorts if r["lifecycle"] == "completed")
    proj_low = sum(r["proj_low"] or 0 for r in cohorts if r["lifecycle"] == "in_flight")
    proj_mid = sum(r["proj_mid"] or 0 for r in cohorts if r["lifecycle"] == "in_flight")
    proj_high = sum(r["proj_high"] or 0 for r in cohorts if r["lifecycle"] == "in_flight")
    projected_mid_revenue = proj_mid * REVENUE_PER_START

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": snapshot_date,
        "revenue_per_start": REVENUE_PER_START,
        "cohorts": cohorts,
        "totals": {
            "booked_starts": booked_starts,
            "booked_revenue": booked_revenue,
            "projected_low_starts": proj_low,
            "projected_mid_starts": proj_mid,
            "projected_high_starts": proj_high,
            "projected_mid_revenue": projected_mid_revenue,
            "combined_mid_revenue": booked_revenue + projected_mid_revenue,
        },
        "reconciliation_warnings": warnings,
    }


def main() -> None:
    ledger = build()
    OUT_JSON.write_text(json.dumps(ledger, indent=2, allow_nan=False), encoding="utf-8")
    t = ledger["totals"]
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"  cohorts: {len(ledger['cohorts'])}  (snapshot {ledger['snapshot_date']})")
    print(f"  booked:    {t['booked_starts']:>4} starts  ${t['booked_revenue']:,}")
    print(f"  projected: {t['projected_mid_starts']:>4} starts  ${t['projected_mid_revenue']:,}  (mid)")
    print(f"  combined mid-case pipeline cash: ${t['combined_mid_revenue']:,}")
    if ledger["reconciliation_warnings"]:
        print(f"  reconciliation warnings: {len(ledger['reconciliation_warnings'])}")
        for w in ledger["reconciliation_warnings"]:
            print(f"    {w['cohort']}: actuals={w['actual_starts']} vs summary={w['v2_starts']}")
    else:
        print("  reconciliation: all completed cohorts agree with the historical summary")


if __name__ == "__main__":
    main()
