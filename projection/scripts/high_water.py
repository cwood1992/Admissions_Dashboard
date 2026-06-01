"""Per-cohort enrollment high-water mark.

The consolidated EnrollList only shows *currently* enrolled students, so no
single weekly snapshot yields total-ever-enrolled. The maximum
`currently_enrolled` ever observed for a cohort across all weekly snapshots is
a stable lower-bound proxy (peak concurrent <= true cumulative, but close in
practice). It serves as the interim ATE denominator until the booked-class CCS
delivers the exact figure, at which point the row is marked superseded.

State file: snapshots/enrollment_high_water.csv
    cohort,high_water_enrolled,as_of_snapshot,superseded_by_booked_ccs,exact_total_ever_enrolled
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import utils

HIGH_WATER_PATH = utils.SNAPSHOTS_DIR / "enrollment_high_water.csv"
_COLUMNS = [
    "cohort",
    "high_water_enrolled",
    "as_of_snapshot",
    "superseded_by_booked_ccs",
    "exact_total_ever_enrolled",
]


def load_high_water(path: Path | None = None) -> pd.DataFrame:
    path = path or HIGH_WATER_PATH
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.read_csv(path)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[_COLUMNS]


def update_high_water(
    cohort_df: pd.DataFrame,
    snapshot_date: str,
    path: Path | None = None,
) -> pd.DataFrame:
    """Fold this week's currently_enrolled into the rolling high-water table.

    Monotonic non-decreasing per cohort: a count that shrank from a prior week
    keeps the prior peak. `as_of_snapshot` is bumped only when a new max is set.
    Cohorts already superseded by a booked-class CCS are left untouched.
    Returns the updated table (also written to disk).
    """
    path = path or HIGH_WATER_PATH
    existing = load_high_water(path)
    # Keep everything as plain dicts so the final DataFrame build is uniform.
    by_cohort: dict[str, dict] = {
        str(row["cohort"]): row.to_dict() for _, row in existing.iterrows()
    }

    snapshot_date = str(snapshot_date)
    for _, row in cohort_df.iterrows():
        cohort = str(row["cohort"])
        current = int(row.get("currently_enrolled", 0) or 0)
        prev = by_cohort.get(cohort)
        if prev is not None and bool(prev.get("superseded_by_booked_ccs", False)):
            continue  # ground truth already recorded; ignore weekly proxy
        if prev is None:
            by_cohort[cohort] = {
                "cohort": cohort,
                "high_water_enrolled": current,
                "as_of_snapshot": snapshot_date,
                "superseded_by_booked_ccs": False,
                "exact_total_ever_enrolled": pd.NA,
            }
        else:
            prev_hw = int(prev.get("high_water_enrolled", 0) or 0)
            if current > prev_hw:
                prev["high_water_enrolled"] = current
                prev["as_of_snapshot"] = snapshot_date
            by_cohort[cohort] = prev

    out = pd.DataFrame(list(by_cohort.values()), columns=_COLUMNS).sort_values("cohort")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def mark_superseded(
    cohort: str,
    exact_total_ever_enrolled: int,
    path: Path | None = None,
) -> pd.DataFrame:
    """Called when a booked-class CCS gives the true total for a cohort."""
    path = path or HIGH_WATER_PATH
    df = load_high_water(path)
    if (df["cohort"] == cohort).any():
        df.loc[df["cohort"] == cohort, "superseded_by_booked_ccs"] = True
        df.loc[df["cohort"] == cohort, "exact_total_ever_enrolled"] = exact_total_ever_enrolled
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [
                        {
                            "cohort": cohort,
                            "high_water_enrolled": exact_total_ever_enrolled,
                            "as_of_snapshot": "",
                            "superseded_by_booked_ccs": True,
                            "exact_total_ever_enrolled": exact_total_ever_enrolled,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.sort_values("cohort").to_csv(path, index=False)
    return df


def annotate_cohort_df(cohort_df: pd.DataFrame, high_water: pd.DataFrame) -> pd.DataFrame:
    """Left-join high_water_enrolled onto the cohort snapshot frame."""
    hw = high_water[["cohort", "high_water_enrolled"]]
    return cohort_df.merge(hw, on="cohort", how="left")
