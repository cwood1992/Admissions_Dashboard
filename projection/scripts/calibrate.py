"""Calibration feedback loop.

After a cohort's start date passes and actuals are known, fold the results back
into baselines. Tracks model accuracy over time in calibration_log.md.

Schema for completed/cohort_actuals.csv:
    cohort, program, actual_starts, total_ever_enrolled,
    wbh_at_start, wbh_that_started,
    vip_at_start, vip_that_started,
    priority_at_start, priority_that_started,
    vip_priority_at_start, vip_priority_that_started,
        (pooled tier: students with VIP or any P-xx and not WBH, counted once;
         the only VIP/P-xx columns calibration reads)
    proj_at_60d, proj_at_30d, proj_at_14d, proj_at_7d,
    calibrated_at  (ISO date; blank = pending)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from scripts import error_bands, utils

DEFAULT_LEARNING_RATE = 0.2  # New observation gets this weight; prior keeps (1-rate).
ESCALATION_ERROR_THRESHOLD = 0.30
ESCALATION_RUN_LENGTH = 3

# --- Accumulation curve calibration -------------------------------------------
# Weekly-resolution bins for building dense enrollment fill curves.
BIN_CENTERS = [0, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91]
BIN_RADIUS = 3  # ±3 days from center
# Cohorts (across ALL completed actuals, not just this run's pending rows)
# that a program needs before its curve is blended. A class start delivers
# exactly one cohort per program, so gating on pending rows alone never fires.
MIN_COHORTS_FOR_CURVE_UPDATE = 2
# Curve observations use the cohort's enrollment high-water mark (peak
# currently_enrolled to date), not currently_enrolled: the curve describes how
# fast enrollment ACCUMULATES, and currently_enrolled collapses in the final
# two weeks as cancellations are processed. projections._project_far divides
# the same high-water figure by the curve, so the two sides stay consistent.
CURVE_NUMERATOR_COL = "high_water_enrolled"


@dataclass
class CalibrationResult:
    cohorts_processed: list[str]
    baseline_deltas: list[str]
    accuracy_lines: list[str]
    escalation_flag: bool
    escalation_reason: str


def _blend(prior: float, observation: float, lr: float = DEFAULT_LEARNING_RATE) -> float:
    return prior * (1 - lr) + observation * lr


def _safe_rate(num, den) -> float | None:
    """Ratio guarded against blanks/NaN/zero. Returns None when not computable
    (e.g. EnrollList-derived actuals with no total_ever_enrolled)."""
    try:
        n = float(num)
        d = float(den)
    except (TypeError, ValueError):
        return None
    if pd.isna(n) or pd.isna(d) or d == 0:
        return None
    return n / d


def _pct_error(projection: float, actual: float) -> float:
    if actual == 0:
        return float("inf") if projection != 0 else 0.0
    return (projection - actual) / actual


def update_ate_rates(
    ate_df: pd.DataFrame,
    completed: pd.DataFrame,
    lr: float = DEFAULT_LEARNING_RATE,
) -> tuple[pd.DataFrame, list[str]]:
    """Update program-level ate_conversion_rates with each completed cohort's
    observed ate-to-start rate. Returns updated df + per-program delta strings.
    """
    df = ate_df.copy()
    deltas: list[str] = []
    for program, group in completed.groupby("program"):
        if program not in df.index:
            continue
        prior_low = float(df.loc[program, "low"])
        prior_mid = float(df.loc[program, "mid"])
        prior_high = float(df.loc[program, "high"])
        for _, row in group.iterrows():
            obs = _safe_rate(row["actual_starts"], row["total_ever_enrolled"])
            if obs is None:
                continue
            new_mid = _blend(prior_mid, obs, lr)
            # Widen low/high to track mid movement proportionally.
            shift = new_mid - prior_mid
            new_low = max(0.0, prior_low + shift)
            new_high = max(new_low, prior_high + shift)
            deltas.append(
                f"{program} ate rate: mid {prior_mid:.4f} -> {new_mid:.4f} "
                f"(observed {obs:.4f} from {row['cohort']}, lr={lr})"
            )
            prior_low, prior_mid, prior_high = new_low, new_mid, new_high
        df.loc[program, "low"] = round(prior_low, 4)
        df.loc[program, "mid"] = round(prior_mid, 4)
        df.loc[program, "high"] = round(prior_high, 4)
    return df, deltas


def update_tier_rates(
    tier_df: pd.DataFrame,
    completed: pd.DataFrame,
    lr: float = DEFAULT_LEARNING_RATE,
) -> tuple[pd.DataFrame, list[str]]:
    """Update confidence_tier_rates from each completed cohort's actual show
    rates. The first non-placeholder update flips the `confidence` field.
    """
    df = tier_df.copy()
    deltas: list[str] = []
    # VIP and P-xx are one pooled tier, counted per student (not per flag) and
    # excluding WBH students, who are already in the WBH floor. The separate
    # vip_*/priority_* columns overlap each other and WBH, so they are never
    # summed here; a row without the pooled columns is skipped for this tier.
    mapping = {
        "WBH": ("wbh_at_start", "wbh_that_started"),
        utils.CONFIDENCE_TIER_VIP_PRIORITY: (
            "vip_priority_at_start",
            "vip_priority_that_started",
        ),
    }
    for tier, (denom_col, num_col) in mapping.items():
        if tier not in df.index:
            continue
        prior_rate = float(df.loc[tier, "conversion_rate"])
        for _, row in completed.iterrows():
            obs = _safe_rate(row.get(num_col), row.get(denom_col))
            if obs is None:
                continue
            new_rate = _blend(prior_rate, obs, lr)
            deltas.append(
                f"{tier} conversion: {prior_rate:.4f} -> {new_rate:.4f} "
                f"(observed {obs:.4f} from {row['cohort']}, lr={lr})"
            )
            prior_rate = new_rate
        df.loc[tier, "conversion_rate"] = round(prior_rate, 4)
        if "placeholder" in str(df.loc[tier, "confidence"]):
            df.loc[tier, "confidence"] = "calibrated"
    return df, deltas


def _accuracy_lines(completed: pd.DataFrame) -> list[str]:
    lines = []
    for _, row in completed.iterrows():
        try:
            actual = float(row["actual_starts"])
        except (TypeError, ValueError):
            continue
        for label, col in [("60d", "proj_at_60d"), ("30d", "proj_at_30d"), ("14d", "proj_at_14d"), ("7d", "proj_at_7d")]:
            if col not in row or pd.isna(row[col]) or str(row[col]).strip() == "":
                continue
            try:
                proj = float(row[col])
            except (TypeError, ValueError):
                continue
            err = _pct_error(proj, actual)
            lines.append(
                f"- {row['cohort']} {label} projection: {int(proj)} -> actual {int(actual)} "
                f"(error {err*100:+.1f}%)"
            )
    return lines


def _check_escalation(
    completed: pd.DataFrame,
    threshold: float = ESCALATION_ERROR_THRESHOLD,
    run_length: int = ESCALATION_RUN_LENGTH,
) -> tuple[bool, str]:
    if "proj_at_30d" not in completed.columns:
        return False, ""
    recent = completed.tail(run_length)
    if len(recent) < run_length:
        return False, ""
    errors = []
    for _, row in recent.iterrows():
        try:
            proj = float(row["proj_at_30d"])
            actual = float(row["actual_starts"])
        except (TypeError, ValueError):
            return False, ""  # incomplete projection history → can't assess
        errors.append(_pct_error(proj, actual))
    if all(e > threshold for e in errors):
        return True, f"Last {run_length} cohorts overshot by >{threshold*100:.0f}% at 30d"
    if all(e < -threshold for e in errors):
        return True, f"Last {run_length} cohorts undershot by >{threshold*100:.0f}% at 30d"
    return False, ""


def _nearest_bin(days_to_start: float) -> int | None:
    """Return the closest weekly bin center, or None if too far from any.

    Skips bin 0 — day-0 fill_pct is definitionally 1.0 and never calibrated.
    """
    candidates = [b for b in BIN_CENTERS if b != 0]
    if not candidates:
        return None
    best = min(candidates, key=lambda b: abs(b - days_to_start))
    if abs(best - days_to_start) > BIN_RADIUS:
        return None
    return best


def extract_cohort_observations(
    cohort: str,
    total_ever_enrolled: int,
    snapshots_dir: Path | None = None,
) -> list[tuple[int, float]]:
    """Extract (bin_center, observed_fill_pct) pairs for a completed cohort.

    Scans all snapshots for rows matching the cohort code. For each,
    computes observed_fill_pct = high_water_enrolled / total_ever_enrolled
    (falling back to currently_enrolled when the snapshot predates the
    high-water column), assigns to the nearest weekly bin (skipping bin 0),
    and returns all observations.
    """
    if total_ever_enrolled <= 0:
        return []

    observations: list[tuple[int, float]] = []
    for _snap_date, snap_path in utils.list_snapshots(snapshots_dir):
        df = pd.read_csv(snap_path)
        rows = df[df["cohort"] == cohort]
        for _, row in rows.iterrows():
            if pd.isna(row.get("days_to_start")) or pd.isna(row.get("currently_enrolled")):
                continue
            dts = float(row["days_to_start"])
            bin_center = _nearest_bin(dts)
            if bin_center is None:
                continue
            # Legacy per-cohort CCS snapshots predate the high-water column but
            # carry their own total_ever_enrolled (incl. cancels); use that
            # before falling back to currently_enrolled.
            numer = None
            for col in (CURVE_NUMERATOR_COL, "total_ever_enrolled", "currently_enrolled"):
                val = row.get(col)
                if val is not None and not pd.isna(val):
                    numer = val
                    break
            fill = float(numer) / total_ever_enrolled
            observations.append((bin_center, fill))
    return observations


def _interpolate_prior(curves_df: pd.DataFrame, program: str, days_to_start: int) -> float:
    """Get the prior fill_pct for a program at a given days_to_start.

    If the exact (program, days_to_start) row exists, returns its value.
    Otherwise, piecewise-linearly interpolates from adjacent existing points
    (same logic as AccumulationCurve.fill_pct in velocity.py).
    """
    sub = curves_df[curves_df["program"] == program].sort_values("days_to_start")
    if sub.empty:
        return 0.0
    # Check for exact match.
    exact = sub[sub["days_to_start"] == days_to_start]
    if not exact.empty:
        return float(exact.iloc[0]["expected_fill_pct"])
    # Piecewise-linear interpolation.
    xs = sub["days_to_start"].to_numpy()
    ys = sub["expected_fill_pct"].to_numpy()
    d = float(days_to_start)
    if d <= xs[0]:
        return float(ys[0])
    if d >= xs[-1]:
        return float(ys[-1])
    for i in range(len(xs) - 1):
        x0, x1 = float(xs[i]), float(xs[i + 1])
        if x0 <= d <= x1:
            y0, y1 = float(ys[i]), float(ys[i + 1])
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (d - x0) / (x1 - x0)
    return float(ys[-1])


def _cohorts_with_curve_coverage(
    actuals: pd.DataFrame, snapshots_dir: Path | None = None
) -> dict[str, set[str]]:
    """Per program, the completed cohorts that have at least one calibratable
    curve observation in the snapshot history. Used for the min-cohorts gate."""
    out: dict[str, set[str]] = {}
    for _, row in actuals.iterrows():
        tee = row.get("total_ever_enrolled")
        try:
            tee_int = int(float(tee))
        except (TypeError, ValueError):
            continue
        if tee_int <= 0:
            continue
        cohort = str(row["cohort"])
        if extract_cohort_observations(cohort, tee_int, snapshots_dir):
            out.setdefault(str(row["program"]), set()).add(cohort)
    return out


def update_accumulation_curves(
    curves_df: pd.DataFrame,
    completed: pd.DataFrame,
    lr: float = DEFAULT_LEARNING_RATE,
    snapshots_dir: Path | None = None,
    history: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Update accumulation curves from completed cohorts' snapshot histories.

    Builds a dense weekly-resolution curve (14 bin centers at 7-day intervals)
    by observing how enrollment ramped up for each completed cohort across
    stored snapshots. Blends observations with the prior curve using the same
    learning-rate approach as ATE/tier calibration.

    ``completed`` holds the cohorts whose observations are blended this run.
    ``history`` (default: ``completed``) is the full set of completed actuals;
    the per-program min-cohorts gate counts coverage across it so the gate can
    pass even when a single class start delivers one cohort per program.

    Returns updated curves DataFrame and list of delta description strings.
    """
    df = curves_df.copy()
    deltas: list[str] = []

    # Collect observations: {(program, bin_center): [fill_pct, ...]}
    obs_by_key: dict[tuple[str, int], list[float]] = {}

    for _, row in completed.iterrows():
        cohort = str(row["cohort"])
        program = str(row["program"])
        tee = row.get("total_ever_enrolled")
        try:
            tee_int = int(float(tee))
        except (TypeError, ValueError):
            continue
        if tee_int <= 0:
            continue

        points = extract_cohort_observations(cohort, tee_int, snapshots_dir)
        for bin_center, fill in points:
            obs_by_key.setdefault((program, bin_center), []).append(fill)

    if not obs_by_key:
        return df.sort_values(["program", "days_to_start"]).reset_index(drop=True), deltas

    gate_frame = history if history is not None else completed
    cohort_count_by_program = _cohorts_with_curve_coverage(gate_frame, snapshots_dir)

    # Blend observations into curves, per program.
    for (program, bin_center), fills in sorted(obs_by_key.items()):
        n_cohorts = len(cohort_count_by_program.get(program, set()))
        if n_cohorts < MIN_COHORTS_FOR_CURVE_UPDATE:
            continue

        observed_mean = sum(fills) / len(fills)
        prior = _interpolate_prior(df, program, bin_center)
        new_val = _blend(prior, observed_mean, lr)

        # Check if this bin center already exists for this program.
        mask = (df["program"] == program) & (df["days_to_start"] == bin_center)
        if mask.any():
            df.loc[mask, "expected_fill_pct"] = round(new_val, 4)
            df.loc[mask, "confidence"] = f"calibrated (N={n_cohorts})"
            df.loc[mask, "source"] = f"calibrated-{date.today().isoformat()}"
        else:
            # New bin center — add a row.
            new_row = pd.DataFrame(
                [
                    {
                        "program": program,
                        "days_to_start": bin_center,
                        "expected_fill_pct": round(new_val, 4),
                        "confidence": f"calibrated (N={n_cohorts})",
                        "source": f"calibrated-{date.today().isoformat()}",
                    }
                ]
            )
            df = pd.concat([df, new_row], ignore_index=True)

        deltas.append(
            f"{program} fill@{bin_center}d: {prior:.4f} -> {new_val:.4f} "
            f"(observed mean {observed_mean:.4f} from {len(fills)} obs, "
            f"N={n_cohorts} cohorts, lr={lr})"
        )

    # Enforce monotonicity: fill_pct must be non-increasing as days_to_start
    # increases (more days out = less enrollment has arrived).
    for program in df["program"].unique():
        sub = df[df["program"] == program].sort_values("days_to_start")
        prev_fill = 1.0  # day 0 is always 1.0
        for idx in sub.index:
            val = float(df.loc[idx, "expected_fill_pct"])
            if int(df.loc[idx, "days_to_start"]) == 0:
                prev_fill = val
                continue
            if val > prev_fill:
                dts = int(df.loc[idx, "days_to_start"])
                deltas.append(
                    f"{program} fill@{dts}d: clamped {val:.4f} -> {prev_fill:.4f} "
                    f"(monotonicity enforcement)"
                )
                df.loc[idx, "expected_fill_pct"] = round(prev_fill, 4)
            prev_fill = float(df.loc[idx, "expected_fill_pct"])

    # Sort so CSV stays clean: program ascending, days_to_start ascending.
    df = df.sort_values(["program", "days_to_start"]).reset_index(drop=True)
    return df, deltas


def _format_log_entry(result: CalibrationResult, run_date: date, title_suffix: str = "") -> str:
    lines = [f"## {run_date.isoformat()} calibration run{title_suffix}", ""]
    lines.append(f"Cohorts processed: {', '.join(result.cohorts_processed) or 'none'}")
    lines.append("")
    if result.accuracy_lines:
        lines.append("### Model accuracy")
        lines.extend(result.accuracy_lines)
        lines.append("")
    if result.baseline_deltas:
        lines.append("### Baseline deltas")
        for d in result.baseline_deltas:
            lines.append(f"- {d}")
        lines.append("")
    if result.escalation_flag:
        lines.append("### ESCALATION FLAG")
        lines.append(f"- {result.escalation_reason}")
        lines.append("")
    return "\n".join(lines)


def calibrate(
    actuals: pd.DataFrame,
    ate_df: pd.DataFrame,
    tier_df: pd.DataFrame,
    lr: float = DEFAULT_LEARNING_RATE,
    curves_df: pd.DataFrame | None = None,
    snapshots_dir: Path | None = None,
    cohorts: list[str] | None = None,
    curves_only: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, CalibrationResult]:
    """Run the feedback loop.

    By default the rows processed are the pending ones (blank calibrated_at).
    ``cohorts`` selects explicit rows instead, regardless of calibrated_at.
    ``curves_only`` skips the ATE/tier blends (returned unchanged) — used to
    replay accumulation-curve calibration for cohorts whose ATE/tier
    observations were already folded in.
    """
    if cohorts is not None:
        pending = actuals[actuals["cohort"].isin(cohorts)]
    else:
        pending = actuals[actuals["calibrated_at"].isna() | (actuals["calibrated_at"] == "")]

    if curves_only:
        new_ate, ate_deltas = ate_df.copy(), []
        new_tier, tier_deltas = tier_df.copy(), []
    else:
        new_ate, ate_deltas = update_ate_rates(ate_df, pending, lr)
        new_tier, tier_deltas = update_tier_rates(tier_df, pending, lr)

    new_curves = None
    curve_deltas: list[str] = []
    if curves_df is not None:
        new_curves, curve_deltas = update_accumulation_curves(
            curves_df, pending, lr, snapshots_dir, history=actuals
        )

    accuracy = _accuracy_lines(pending)
    escalated, reason = _check_escalation(actuals)

    result = CalibrationResult(
        cohorts_processed=list(pending["cohort"]),
        baseline_deltas=ate_deltas + tier_deltas + curve_deltas,
        accuracy_lines=accuracy,
        escalation_flag=escalated,
        escalation_reason=reason,
    )
    return new_ate, new_tier, new_curves, result


def write_calibration_log(
    log_path: Path,
    result: CalibrationResult,
    run_date: date | None = None,
    title_suffix: str = "",
) -> None:
    run_date = run_date or date.today()
    entry = _format_log_entry(result, run_date, title_suffix)
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
    else:
        existing = "# Calibration log\n\n"
    log_path.write_text(existing + entry + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run calibration feedback loop.")
    parser.add_argument(
        "--actuals",
        default=None,
        help="Path to completed/cohort_actuals.csv (default).",
    )
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--dry-run", action="store_true", help="Compute deltas without writing.")
    parser.add_argument(
        "--cohorts",
        default=None,
        help="Comma-separated cohort codes to process instead of the pending rows "
        "(calibrated_at is left untouched).",
    )
    parser.add_argument(
        "--curves-only",
        action="store_true",
        help="Only blend accumulation curves; ATE/tier baselines and calibrated_at "
        "are not modified. Use with --cohorts to replay curve calibration.",
    )
    args = parser.parse_args()

    cohorts = [c.strip() for c in args.cohorts.split(",") if c.strip()] if args.cohorts else None

    actuals_path = Path(args.actuals) if args.actuals else utils.COMPLETED_DIR / "cohort_actuals.csv"
    actuals = pd.read_csv(actuals_path)
    ate_df = pd.read_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv").set_index("program")
    tier_df = pd.read_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv").set_index("tier")

    curves_df = pd.read_csv(utils.BASELINES_DIR / "accumulation_curves.csv")
    new_ate, new_tier, new_curves, result = calibrate(
        actuals, ate_df, tier_df, args.learning_rate, curves_df,
        cohorts=cohorts, curves_only=args.curves_only,
    )
    log_path = utils.PROJECT_ROOT / "calibration_log.md"
    title_suffix = " (curves only)" if args.curves_only else ""

    if args.dry_run:
        print(_format_log_entry(result, date.today(), title_suffix))
        return

    if not args.curves_only:
        new_ate.to_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv")
        new_tier.to_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv")
    if new_curves is not None:
        new_curves.to_csv(utils.BASELINES_DIR / "accumulation_curves.csv", index=False)
    if cohorts is None and not args.curves_only:
        # Coerce to object dtype so a date string can be written even when the
        # column was inferred as float64 (all-NaN from empty cells).
        actuals["calibrated_at"] = actuals["calibrated_at"].astype("object")
        pending_mask = actuals["calibrated_at"].isna() | (actuals["calibrated_at"] == "")
        actuals.loc[pending_mask, "calibrated_at"] = date.today().isoformat()
        actuals.to_csv(actuals_path, index=False)
    write_calibration_log(log_path, result, title_suffix=title_suffix)
    # Band widths are measured on the current model, so they are re-measured
    # whenever the baselines it runs on (or the set of completed cohorts) change.
    bands = error_bands.rebuild()
    print("Rebuilt projection error bands:")
    print(bands[["days_lo", "days_hi", "n_cohorts", "band_rms_z", "source"]].to_string(index=False))
    print(f"Processed {len(result.cohorts_processed)} cohorts. Log: {log_path}")
    if result.escalation_flag:
        print(f"ESCALATION: {result.escalation_reason}")


if __name__ == "__main__":
    main()
