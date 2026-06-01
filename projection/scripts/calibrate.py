"""Calibration feedback loop.

After a cohort's start date passes and actuals are known, fold the results back
into baselines. Tracks model accuracy over time in calibration_log.md.

Schema for completed/cohort_actuals.csv:
    cohort, program, actual_starts, total_ever_enrolled,
    wbh_at_start, wbh_that_started,
    vip_at_start, vip_that_started,
    priority_at_start, priority_that_started,
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

from scripts import utils

DEFAULT_LEARNING_RATE = 0.2  # New observation gets this weight; prior keeps (1-rate).
ESCALATION_ERROR_THRESHOLD = 0.30
ESCALATION_RUN_LENGTH = 3


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
    mapping = {
        "WBH": ("wbh_at_start", "wbh_that_started"),
        "VIP": ("vip_at_start", "vip_that_started"),
        "Priority": ("priority_at_start", "priority_that_started"),
    }
    for tier, (denom_col, num_col) in mapping.items():
        if tier not in df.index:
            continue
        prior_rate = float(df.loc[tier, "conversion_rate"])
        for _, row in completed.iterrows():
            obs = _safe_rate(row[num_col], row[denom_col])
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


def _format_log_entry(result: CalibrationResult, run_date: date) -> str:
    lines = [f"## {run_date.isoformat()} calibration run", ""]
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
) -> tuple[pd.DataFrame, pd.DataFrame, CalibrationResult]:
    pending = actuals[actuals["calibrated_at"].isna() | (actuals["calibrated_at"] == "")]
    new_ate, ate_deltas = update_ate_rates(ate_df, pending, lr)
    new_tier, tier_deltas = update_tier_rates(tier_df, pending, lr)
    accuracy = _accuracy_lines(pending)
    escalated, reason = _check_escalation(actuals)

    result = CalibrationResult(
        cohorts_processed=list(pending["cohort"]),
        baseline_deltas=ate_deltas + tier_deltas,
        accuracy_lines=accuracy,
        escalation_flag=escalated,
        escalation_reason=reason,
    )
    return new_ate, new_tier, result


def write_calibration_log(
    log_path: Path,
    result: CalibrationResult,
    run_date: date | None = None,
) -> None:
    run_date = run_date or date.today()
    entry = _format_log_entry(result, run_date)
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
    args = parser.parse_args()

    actuals_path = Path(args.actuals) if args.actuals else utils.COMPLETED_DIR / "cohort_actuals.csv"
    actuals = pd.read_csv(actuals_path)
    ate_df = pd.read_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv").set_index("program")
    tier_df = pd.read_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv").set_index("tier")

    new_ate, new_tier, result = calibrate(actuals, ate_df, tier_df, args.learning_rate)
    log_path = utils.PROJECT_ROOT / "calibration_log.md"

    if args.dry_run:
        print(_format_log_entry(result, date.today()))
        return

    new_ate.to_csv(utils.BASELINES_DIR / "ate_conversion_rates.csv")
    new_tier.to_csv(utils.BASELINES_DIR / "confidence_tier_rates.csv")
    # Coerce to object dtype so a date string can be written even when the
    # column was inferred as float64 (all-NaN from empty cells).
    actuals["calibrated_at"] = actuals["calibrated_at"].astype("object")
    pending_mask = actuals["calibrated_at"].isna() | (actuals["calibrated_at"] == "")
    actuals.loc[pending_mask, "calibrated_at"] = date.today().isoformat()
    actuals.to_csv(actuals_path, index=False)
    write_calibration_log(log_path, result)
    print(f"Processed {len(result.cohorts_processed)} cohorts. Log: {log_path}")
    if result.escalation_flag:
        print(f"ESCALATION: {result.escalation_reason}")


if __name__ == "__main__":
    main()
