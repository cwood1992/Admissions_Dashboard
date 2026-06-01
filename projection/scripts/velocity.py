from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts import utils

VELOCITY_TOLERANCE = 0.10  # ±10% band around expected = "on-track"


@dataclass(frozen=True)
class AccumulationCurve:
    """Piecewise-linear expected_fill_pct as a function of days_to_start."""

    rows: pd.DataFrame  # columns: program, days_to_start, expected_fill_pct, confidence

    def fill_pct(self, program: str, days_to_start: float) -> float:
        sub = self.rows[self.rows["program"] == program].sort_values("days_to_start")
        if sub.empty:
            raise ValueError(f"No accumulation curve for program={program!r}")
        d = float(days_to_start)
        xs = sub["days_to_start"].to_numpy()
        ys = sub["expected_fill_pct"].to_numpy()
        if d <= xs[0]:
            return float(ys[0])
        if d >= xs[-1]:
            return float(ys[-1])
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            if x0 <= d <= x1:
                y0, y1 = ys[i], ys[i + 1]
                if x1 == x0:
                    return float(y0)
                return float(y0 + (y1 - y0) * (d - x0) / (x1 - x0))
        return float(ys[-1])


def load_accumulation_curves(path: Path | None = None) -> AccumulationCurve:
    path = path or utils.BASELINES_DIR / "accumulation_curves.csv"
    return AccumulationCurve(rows=pd.read_csv(path))


def classify_velocity(weekly: float, expected: float, tolerance: float = VELOCITY_TOLERANCE) -> str:
    if pd.isna(weekly) or pd.isna(expected):
        return "unknown"
    if expected <= 0:
        return "unknown"
    if weekly > expected * (1 + tolerance):
        return "above"
    if weekly < expected * (1 - tolerance):
        return "below"
    return "on-track"


def classify_velocity_from_snapshot(
    cohort_df: pd.DataFrame,
    curve: AccumulationCurve,
    position_averages: dict[str, int],
    snapshot_gap_days: int = 7,
) -> pd.DataFrame:
    """EnrollList path: `weekly_velocity` is already on the frame (students
    enrolled within the last 7 days, derived from Current Enroll Date at ingest
    time). We only need to compute the expected velocity from the accumulation
    curve and classify. No prior snapshot required.
    """
    out = cohort_df.copy()
    if "weekly_velocity" not in out.columns:
        out["weekly_velocity"] = float("nan")

    def expected_count(days_to_start, program: str, cohort: str) -> float:
        pos_avg = position_averages.get(cohort)
        if pos_avg is None or pd.isna(days_to_start):
            return float("nan")
        return pos_avg * curve.fill_pct(program, float(days_to_start))

    expected_now = out.apply(
        lambda r: expected_count(r["days_to_start"], r["program"], r["cohort"]), axis=1
    )
    expected_prior = out.apply(
        lambda r: expected_count(
            (r["days_to_start"] + snapshot_gap_days)
            if pd.notna(r["days_to_start"])
            else r["days_to_start"],
            r["program"],
            r["cohort"],
        ),
        axis=1,
    )
    out["expected_weekly_velocity"] = expected_now - expected_prior
    out["velocity_vs_historical"] = out.apply(
        lambda r: classify_velocity(r["weekly_velocity"], r["expected_weekly_velocity"]),
        axis=1,
    )
    return out


def compute_velocity(
    current_df: pd.DataFrame,
    prior_df: pd.DataFrame,
    curve: AccumulationCurve,
    position_averages: dict[str, int],
    snapshot_gap_days: int = 7,
) -> pd.DataFrame:
    """Legacy week-over-week derivation (old per-cohort CCS format).

    Retained for re-ingesting pre-EnrollList snapshots. The EnrollList path
    uses classify_velocity_from_snapshot instead.
    """
    if "total_ever_enrolled" not in prior_df.columns:
        raise ValueError("prior_df must include total_ever_enrolled")
    merged = current_df.merge(
        prior_df[["cohort", "total_ever_enrolled"]].rename(
            columns={"total_ever_enrolled": "total_ever_enrolled_prior"}
        ),
        on="cohort",
        how="left",
    )

    merged["weekly_velocity"] = (
        merged["total_ever_enrolled"] - merged["total_ever_enrolled_prior"]
    )

    def expected_count(days_to_start: float, program: str, cohort: str) -> float:
        pos_avg = position_averages.get(cohort)
        if pos_avg is None:
            return float("nan")
        return pos_avg * curve.fill_pct(program, days_to_start)

    expected_now = merged.apply(
        lambda r: expected_count(r["days_to_start"], r["program"], r["cohort"]), axis=1
    )
    expected_prior = merged.apply(
        lambda r: expected_count(r["days_to_start"] + snapshot_gap_days, r["program"], r["cohort"]),
        axis=1,
    )
    merged["expected_weekly_velocity"] = expected_now - expected_prior
    merged["velocity_vs_historical"] = merged.apply(
        lambda r: classify_velocity(r["weekly_velocity"], r["expected_weekly_velocity"]), axis=1
    )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute weekly velocity vs historical curves.")
    parser.add_argument("--date", required=True, help="Current snapshot date (YYYY-MM-DD).")
    parser.add_argument("--prior-date", required=True, help="Prior snapshot date (YYYY-MM-DD).")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    from scripts.projections import load_position_averages

    current = pd.read_csv(utils.SNAPSHOTS_DIR / f"{args.date}_snapshot.csv")
    prior = pd.read_csv(utils.SNAPSHOTS_DIR / f"{args.prior_date}_snapshot.csv")
    curve = load_accumulation_curves()
    pos = load_position_averages()
    result = compute_velocity(current, prior, curve, pos)
    out = Path(args.out) if args.out else utils.SNAPSHOTS_DIR / f"{args.date}_snapshot.csv"
    result.to_csv(out, index=False)
    print(f"Wrote velocity-enriched snapshot to {out}")


if __name__ == "__main__":
    main()
