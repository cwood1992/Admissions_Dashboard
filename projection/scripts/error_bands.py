"""Low/high bands sized from observed projection error.

The regimes in ``projections.py`` produce the mid. Their own low/high came from
the ATE spread or the tier stack and contained the actual under half the time
(reports/projection_accuracy.md), so the published band is now:

    half_width = k * rms_z(days-to-start bucket) * sqrt(mid)
    z          = (actual_starts - proj_mid) / sqrt(proj_mid)

``rms_z`` is measured by replaying the CURRENT model over every stored snapshot
of every completed cohort (one z per cohort per bucket, the median, so a cohort
with nine weekly rows counts once), pooled across programs. sqrt(mid) scaling
keeps 3-start cohorts from dominating. Replay rather than published error,
because published far-regime errors grade logic retired on 2026-09-14. The
replay is partly in-sample (curves were calibrated on the same cohorts), so
far-out widths are, if anything, understated.

Parameters (k, buckets, minimum cohorts) live in
baselines/projection_band_config.json. The table is rebuilt by calibrate at
every class start, or by hand:

    uv run python -m scripts.error_bands
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from scripts import utils

CONFIG_FILENAME = "projection_band_config.json"
TABLE_FILENAME = "projection_error_bands.csv"

TABLE_COLUMNS = [
    "days_lo", "days_hi", "n_cohorts", "rms_z", "band_rms_z", "source",
    "classes", "built_on",
]


@dataclass(frozen=True)
class BandConfig:
    k: float
    buckets: list[tuple[int, int | None]]
    min_cohorts_per_bucket: int
    target_coverage: float | None = None


@dataclass(frozen=True)
class Band:
    days_lo: int
    days_hi: int | None
    rms_z: float
    n_cohorts: int

    @property
    def label(self) -> str:
        return f"{self.days_lo}+d" if self.days_hi is None else f"{self.days_lo}-{self.days_hi}d"


@dataclass(frozen=True)
class ErrorBands:
    k: float
    bands: list[Band]

    def band_for(self, days_to_start: int) -> Band | None:
        for b in self.bands:
            if days_to_start >= b.days_lo and (b.days_hi is None or days_to_start <= b.days_hi):
                return b
        return None

    def apply(self, mid: int, days_to_start: int) -> tuple[int, int, float, Band] | None:
        """(low, high, half_width, band) around ``mid``; None when no bucket
        has enough history, so the caller keeps the regime's own band."""
        band = self.band_for(days_to_start)
        if band is None:
            return None
        half = self.k * band.rms_z * math.sqrt(max(mid, 1))
        low = max(0, math.floor(mid - half))
        high = math.ceil(mid + half)
        return low, high, half, band


def load_config(path: Path | None = None) -> BandConfig:
    raw = json.loads((path or utils.BASELINES_DIR / CONFIG_FILENAME).read_text(encoding="utf-8"))
    return BandConfig(
        k=float(raw["k"]),
        buckets=[(int(lo), None if hi is None else int(hi)) for lo, hi in raw["buckets"]],
        min_cohorts_per_bucket=int(raw["min_cohorts_per_bucket"]),
        target_coverage=raw.get("target_coverage"),
    )


def load_error_bands(
    table_path: Path | None = None, config_path: Path | None = None
) -> ErrorBands | None:
    """None when the table has not been built yet (fresh checkout, tests)."""
    table_path = table_path or utils.BASELINES_DIR / TABLE_FILENAME
    if not table_path.exists():
        return None
    df = pd.read_csv(table_path)
    df = df[pd.notna(df["band_rms_z"])]
    if df.empty:
        return None
    bands = [
        Band(
            days_lo=int(r.days_lo),
            days_hi=None if pd.isna(r.days_hi) else int(r.days_hi),
            rms_z=float(r.band_rms_z),
            n_cohorts=int(r.n_cohorts),
        )
        for r in df.itertuples()
    ]
    return ErrorBands(k=load_config(config_path).k, bands=bands)


# --------------------------------------------------------------------------
# Roll-ups
# --------------------------------------------------------------------------

def combine_independent(
    ranges: Iterable[tuple[float, float, float]],
) -> tuple[float, float, float]:
    """(low, mid, high) of a sum of cohort ranges, treating cohort errors as
    independent: mids add, the downside and upside distances add in quadrature.
    Summing lows and highs instead assumes every cohort misses the same way at
    once. Cohorts are not fully independent, so the truth sits between the two.
    A booked cohort (low = mid = high) adds nothing to the width."""
    mid = down = up = 0.0
    for low, m, high in ranges:
        mid += m
        down += (m - low) ** 2
        up += (high - m) ** 2
    return mid - math.sqrt(down), mid, mid + math.sqrt(up)


def combine_independent_int(ranges: Iterable[tuple[float, float, float]]) -> tuple[int, int, int]:
    low, mid, high = combine_independent(ranges)
    mid_i = int(round(mid))
    return min(mid_i, int(round(low))), mid_i, max(mid_i, int(round(high)))


# --------------------------------------------------------------------------
# Building the table (replay of the current model)
# --------------------------------------------------------------------------

def replay_errors(
    snapshots_dir: Path | None = None, completed_dir: Path | None = None
) -> pd.DataFrame:
    """One row per completed cohort x stored snapshot before its start, with the
    mid the CURRENT model produces from that snapshot's inputs and its z."""
    from scripts import accuracy_report, projections  # lazy: projections imports this module

    actuals = accuracy_report.load_actuals(completed_dir)
    proj_cols = ["proj_low", "proj_mid", "proj_high", "projection_basis"]
    rows: list[dict] = []
    for snap_date, path in utils.list_snapshots(snapshots_dir):
        df = pd.read_csv(path)
        df = df.drop(columns=[c for c in proj_cols if c in df.columns])
        df = df[df["cohort"].isin(actuals) & (df["days_to_start"] >= 0)]
        if df.empty:
            continue
        replayed = projections.project_dataframe(df, bands=None)
        rows.extend(accuracy_report.grade_snapshot(replayed, snap_date, actuals))
    out = pd.DataFrame(rows)
    if len(out):
        out["z"] = (out["actual_starts"] - out["proj_mid"]) / out["proj_mid"].clip(lower=1) ** 0.5
    return out


def _bucket_index(days: int, buckets: list[tuple[int, int | None]]) -> int | None:
    for i, (lo, hi) in enumerate(buckets):
        if days >= lo and (hi is None or days <= hi):
            return i
    return None


def build_band_table(
    errors: pd.DataFrame, config: BandConfig, built_on: date | None = None
) -> pd.DataFrame:
    """rms of the per-cohort median z in each bucket. A bucket with too few
    cohorts borrows the larger rms_z of its qualifying neighbours."""
    built = (built_on or date.today()).isoformat()
    stats: list[dict] = []
    for i, (lo, hi) in enumerate(config.buckets):
        n, rms, classes = 0, None, ""
        if len(errors):
            idx = errors["days_to_start"].map(lambda d: _bucket_index(int(d), config.buckets))
            in_bucket = errors[idx == i]
            per_cohort = in_bucket.groupby("cohort")["z"].median()
            n = len(per_cohort)
            if n:
                rms = float((per_cohort ** 2).mean() ** 0.5)
                nums = sorted(in_bucket["class_number"].dropna().astype(int).unique())
                classes = f"{nums[0]}-{nums[-1]}" if nums else ""
        stats.append({"days_lo": lo, "days_hi": hi, "n_cohorts": n, "rms_z": rms, "classes": classes})

    for i, s in enumerate(stats):
        if s["n_cohorts"] >= config.min_cohorts_per_bucket:
            s["band_rms_z"], s["source"] = s["rms_z"], "own"
            continue
        neighbours = [
            stats[j] for j in (i - 1, i + 1)
            if 0 <= j < len(stats) and stats[j]["n_cohorts"] >= config.min_cohorts_per_bucket
        ]
        if neighbours:
            donor = max(neighbours, key=lambda x: x["rms_z"])
            s["band_rms_z"] = donor["rms_z"]
            s["source"] = f"borrowed:{donor['days_lo']}d"
        else:
            s["band_rms_z"], s["source"] = None, "insufficient"
    table = pd.DataFrame(stats)
    table["built_on"] = built
    table["days_hi"] = table["days_hi"].astype("Int64")
    for col in ("rms_z", "band_rms_z"):
        table[col] = table[col].astype(float).round(4)
    return table[TABLE_COLUMNS]


def rebuild(
    snapshots_dir: Path | None = None,
    completed_dir: Path | None = None,
    table_path: Path | None = None,
    config_path: Path | None = None,
) -> pd.DataFrame:
    config = load_config(config_path)
    table = build_band_table(replay_errors(snapshots_dir, completed_dir), config)
    table.to_csv(table_path or utils.BASELINES_DIR / TABLE_FILENAME, index=False)
    return table


def main() -> None:
    table = rebuild()
    print(table.to_string(index=False))
    print(f"Wrote {utils.BASELINES_DIR / TABLE_FILENAME}")


if __name__ == "__main__":
    main()
