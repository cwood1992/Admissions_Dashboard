from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts import error_bands, utils
from scripts.velocity import AccumulationCurve, load_accumulation_curves


@dataclass(frozen=True)
class Projection:
    proj_low: int
    proj_mid: int
    proj_high: int
    projection_basis: str


@dataclass(frozen=True)
class AteRange:
    low: float
    mid: float
    high: float


@dataclass(frozen=True)
class ConfidenceTierRates:
    wbh_show_rate: float
    vip_conversion_rate: float
    priority_conversion_rate: float
    is_placeholder: bool


def load_position_averages(
    path: Path | None = None,
    cohort_codes: list[str] | None = None,
) -> dict[str, int]:
    """Load position averages and expand into a per-cohort lookup.

    The on-disk file is keyed by (program, position) — that's the conceptually
    correct shape, since position averages describe calendar slots not specific
    cohort numbers. This function expands the table into a {cohort_code:
    position_average} dict so callers can look up by the cohort code they
    already have. The set of cohort codes to expand to defaults to the open
    cohorts listed in program_start_dates_2026.csv.
    """
    path = path or utils.BASELINES_DIR / "position_averages.csv"
    df = pd.read_csv(path)
    by_pos = {
        (str(row["program"]), int(row["position"])): int(row["position_average"])
        for _, row in df.iterrows()
    }

    if cohort_codes is None:
        # Late import: ingest.py loads program_start_dates and we want to avoid
        # a hard import cycle. Callers can pass cohort_codes explicitly to skip
        # this lookup (useful in tests).
        from scripts.ingest import load_program_start_dates

        cohort_codes = list(load_program_start_dates().keys())

    out: dict[str, int] = {}
    for cohort in cohort_codes:
        try:
            program = utils.program_for_cohort(cohort)
            position = utils.position_for_cohort(cohort)
        except ValueError:
            continue
        key = (program, position)
        if key in by_pos:
            out[cohort] = by_pos[key]
    return out


def load_ate_rates(path: Path | None = None) -> dict[str, AteRange]:
    path = path or utils.BASELINES_DIR / "ate_conversion_rates.csv"
    df = pd.read_csv(path)
    return {
        row["program"]: AteRange(low=row["low"], mid=row["mid"], high=row["high"])
        for _, row in df.iterrows()
    }


def load_confidence_tier_rates(path: Path | None = None) -> ConfidenceTierRates:
    path = path or utils.BASELINES_DIR / "confidence_tier_rates.csv"
    df = pd.read_csv(path).set_index("tier")
    return ConfidenceTierRates(
        wbh_show_rate=float(df.loc["WBH", "conversion_rate"]),
        vip_conversion_rate=float(df.loc["VIP", "conversion_rate"]),
        priority_conversion_rate=float(df.loc["Priority", "conversion_rate"]),
        is_placeholder=df["confidence"].str.contains("placeholder").any(),
    )


def project_trivial(currently_enrolled: int, position_avg: int | None) -> Projection:
    """Crude M3 placeholder. Kept for tests; M5 replaces production calls."""
    if position_avg is None:
        pos = max(currently_enrolled, 1)
        basis = (
            f"trivial-v0: no position_average for cohort, fallback=current_enrolled"
            f" ({currently_enrolled}); needs baseline seeding"
        )
    else:
        pos = position_avg
        basis = (
            f"trivial-v0: pos_avg={pos}, current={currently_enrolled}, "
            f"bounds=±15% floored at current"
        )

    low = max(currently_enrolled, round(pos * 0.85))
    mid = max(low, round(pos))
    high = max(mid, round(pos * 1.10))
    return Projection(int(low), int(mid), int(high), basis)


REGIME_FAR = "far-30+"
REGIME_MEDIUM = "medium-14-30"
REGIME_NEAR = "near-<14"

FAR_REGIME_THRESHOLD = 30
NEAR_REGIME_THRESHOLD = 14

# In the far regime, blend the accumulation-derived projection with the
# position average as a Bayesian prior. The position average gets weight
# POSITION_PRIOR_WEIGHT, the accumulation-derived projection gets (1 - W).
POSITION_PRIOR_WEIGHT = 2 / 3


def _enforce_order(low: int, mid: int, high: int) -> tuple[int, int, int]:
    mid = max(low, mid)
    high = max(mid, high)
    return low, mid, high


FAR_REGIME_PROJECTION_CAP_MULTIPLIER = 2.5
"""Cap the accumulation-derived STARTS projection at this multiple of
position_avg. Safety net against a noisy fill_pct; with ATE applied it should
rarely bind."""

FAR_REGIME_MIN_FILL_PCT = 0.15
"""Below this expected fill (roughly 90+ days out) a handful of early
enrollments divided by a tiny fill_pct is noise, so the far regime uses the
position average alone. The spec's "weight toward position average, adjusted
by current fill status" — the accumulation term only enters once the cohort is
meaningfully filling."""


def _accumulated_enrolled(row: pd.Series) -> int:
    """Enrollment figure the accumulation curve is divided into: the cohort's
    high-water mark (peak currently_enrolled to date, attached by
    high_water.annotate_cohort_df). The curve is calibrated on the same figure
    (calibrate.CURVE_NUMERATOR_COL), because currently_enrolled collapses in
    the final two weeks as cancellations land. Falls back to currently_enrolled
    when the column is absent."""
    hw = row.get("high_water_enrolled")
    if hw is None or pd.isna(hw):
        return int(row["currently_enrolled"])
    return max(int(hw), int(row["currently_enrolled"]))


def _project_far(
    currently_enrolled: int,
    position_avg: int,
    days_to_start: int,
    program: str,
    ate: AteRange,
    curve: AccumulationCurve,
) -> Projection:
    """Accumulation-curve regime, all in STARTS units:

    projected_enrolled = accumulated (high-water) / fill_pct   -> enrollments
    projected_starts   = projected_enrolled * ate.mid          -> starts
    capped at 2.5x position_avg, then blended 1/3 with the position_avg prior.
    Below FAR_REGIME_MIN_FILL_PCT the position average is used alone.
    """
    fill_pct = curve.fill_pct(program, float(days_to_start))
    capped = False
    if fill_pct >= FAR_REGIME_MIN_FILL_PCT:
        projected_enrolled = currently_enrolled / fill_pct
        projected_starts = projected_enrolled * ate.mid
        cap = FAR_REGIME_PROJECTION_CAP_MULTIPLIER * position_avg
        if projected_starts > cap:
            projected_starts = cap
            capped = True
        blended = (
            (1 - POSITION_PRIOR_WEIGHT) * projected_starts
            + POSITION_PRIOR_WEIGHT * position_avg
        )
        cap_note = f", capped@{FAR_REGIME_PROJECTION_CAP_MULTIPLIER:.1f}x_pos_avg" if capped else ""
        basis = (
            f"{REGIME_FAR}: accum_fill@{days_to_start}d={fill_pct:.2f}, "
            f"proj_enrolled={projected_enrolled:.0f} x ate_mid={ate.mid:.3f} "
            f"= {projected_starts:.1f} starts{cap_note}, blended_with_pos_avg={blended:.1f} "
            f"(prior_weight={POSITION_PRIOR_WEIGHT:.2f})"
        )
    else:
        blended = float(position_avg)
        basis = (
            f"{REGIME_FAR}: accum_fill@{days_to_start}d={fill_pct:.2f} below "
            f"{FAR_REGIME_MIN_FILL_PCT:.2f} floor; position_avg={position_avg} only"
        )
    # Scenario spread derived from the ate range width relative to mid.
    spread = (ate.high - ate.low) / ate.mid if ate.mid else 0.25
    low = max(0, round(blended * (1 - spread / 2)))
    mid = round(blended)
    high = round(blended * (1 + spread / 2))
    low, mid, high = _enforce_order(low, mid, high)
    return Projection(low, mid, high, basis)


def _project_medium(
    currently_enrolled: int,
    position_avg: int,
    days_to_start: int,
    program: str,
    wbh: int,
    vip: int,
    priority: int,
    ate: AteRange,
    curve: AccumulationCurve,
    tiers: ConfidenceTierRates,
) -> Projection:
    far = _project_far(currently_enrolled, position_avg, days_to_start, program, ate, curve)
    tier_low = wbh * tiers.wbh_show_rate
    tier_mid = tier_low + vip * tiers.vip_conversion_rate
    tier_high = tier_mid + priority * tiers.priority_conversion_rate
    low = round((far.proj_low + tier_low) / 2)
    mid = round((far.proj_mid + tier_mid) / 2)
    high = round((far.proj_high + tier_high) / 2)
    low, mid, high = _enforce_order(low, mid, high)
    basis = (
        f"{REGIME_MEDIUM}: blend(accum={far.proj_mid}, tier_mid={tier_mid:.1f}); "
        f"WBH={wbh},VIP={vip},Priority={priority}"
    )
    if tiers.is_placeholder:
        basis += " [tier rates are placeholders, data-starved]"
    return Projection(low, mid, high, basis)


def _project_near(
    wbh: int,
    vip: int,
    priority: int,
    tiers: ConfidenceTierRates,
) -> Projection:
    floor = wbh * tiers.wbh_show_rate
    midline = floor + vip * tiers.vip_conversion_rate
    upside = midline + priority * tiers.priority_conversion_rate
    low = max(0, round(floor))
    mid = round(midline)
    high = round(upside)
    low, mid, high = _enforce_order(low, mid, high)
    basis = (
        f"{REGIME_NEAR}: WBH({wbh})×{tiers.wbh_show_rate:.2f} floor, "
        f"VIP({vip})×{tiers.vip_conversion_rate:.2f} + "
        f"Priority({priority})×{tiers.priority_conversion_rate:.2f} upside"
    )
    if tiers.is_placeholder:
        basis += " [tier rates are placeholders, data-starved]"
    return Projection(low, mid, high, basis)


def project_three_regime(
    row: pd.Series,
    position_avg: int | None,
    ate: AteRange | None,
    curve: AccumulationCurve,
    tiers: ConfidenceTierRates,
) -> Projection:
    days = int(row["days_to_start"])
    currently_enrolled = int(row["currently_enrolled"])
    # Accumulation regimes (far/medium) divide the high-water mark by the
    # fill curve; the trivial fallback keeps using currently_enrolled.
    accumulated = _accumulated_enrolled(row)
    program = str(row["program"])
    wbh = int(row.get("wbh_count", 0) or 0)
    vip = int(row.get("vip_count", 0) or 0)
    priority = int(
        (row.get("p_fa_count", 0) or 0)
        + (row.get("p_va_count", 0) or 0)
        + (row.get("p_acc_count", 0) or 0)
        + (row.get("p_adm_count", 0) or 0)
    )

    if position_avg is None or ate is None:
        # Fall back to trivial when baseline data is missing.
        proj = project_trivial(currently_enrolled, position_avg)
        return Projection(
            proj.proj_low,
            proj.proj_mid,
            proj.proj_high,
            f"{proj.projection_basis} [no baseline for program={program!r}; using trivial]",
        )

    if days >= FAR_REGIME_THRESHOLD:
        return _project_far(accumulated, position_avg, days, program, ate, curve)
    if days >= NEAR_REGIME_THRESHOLD:
        return _project_medium(
            accumulated,
            position_avg,
            days,
            program,
            wbh,
            vip,
            priority,
            ate,
            curve,
            tiers,
        )
    return _project_near(wbh, vip, priority, tiers)


BANDS_FROM_BASELINES = "baselines"
"""Default for ``project_dataframe(bands=...)``: load the observed-error band
table from baselines/. Pass ``None`` to keep each regime's own low/high (the
band replay in error_bands does, since it only needs the mid)."""


def apply_error_band(
    proj: Projection, days_to_start: int, bands: error_bands.ErrorBands | None
) -> Projection:
    """Replace the regime's low/high with the band sized from observed error
    around the unchanged mid. The regime's own band is kept when there is no
    table or no bucket with enough history."""
    if bands is None:
        return proj
    sized = bands.apply(proj.proj_mid, days_to_start)
    if sized is None:
        return proj
    low, high, half, band = sized
    low, mid, high = _enforce_order(low, proj.proj_mid, high)
    basis = (
        f"{proj.projection_basis} | band +/-{half:.1f} = {bands.k:.2f} x rms_z "
        f"{band.rms_z:.2f} ({band.label}, n={band.n_cohorts} cohorts) x sqrt(mid)"
    )
    return Projection(low, mid, high, basis)


def project_dataframe(
    cohort_df: pd.DataFrame,
    position_averages: dict[str, int] | None = None,
    ate_rates: dict[str, AteRange] | None = None,
    curve: AccumulationCurve | None = None,
    tiers: ConfidenceTierRates | None = None,
    bands: error_bands.ErrorBands | str | None = BANDS_FROM_BASELINES,
) -> pd.DataFrame:
    pos = position_averages if position_averages is not None else load_position_averages()
    ate = ate_rates if ate_rates is not None else load_ate_rates()
    curve = curve if curve is not None else load_accumulation_curves()
    tiers = tiers if tiers is not None else load_confidence_tier_rates()
    if bands == BANDS_FROM_BASELINES:
        bands = error_bands.load_error_bands()

    proj_rows = []
    for _, row in cohort_df.iterrows():
        proj = project_three_regime(
            row,
            pos.get(row["cohort"]),
            ate.get(row["program"]),
            curve,
            tiers,
        )
        proj = apply_error_band(proj, int(row["days_to_start"]), bands)
        proj_rows.append(
            {
                "cohort": row["cohort"],
                "proj_low": proj.proj_low,
                "proj_mid": proj.proj_mid,
                "proj_high": proj.proj_high,
                "projection_basis": proj.projection_basis,
            }
        )
    return cohort_df.merge(pd.DataFrame(proj_rows), on="cohort")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add start projections to a snapshot CSV.")
    parser.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument(
        "--snapshot-csv",
        default=None,
        help="Path to snapshot CSV (defaults to snapshots/<date>_snapshot.csv).",
    )
    parser.add_argument("--out", default=None, help="Output path (defaults to in-place overwrite).")
    args = parser.parse_args()

    snap_path = (
        Path(args.snapshot_csv)
        if args.snapshot_csv
        else utils.SNAPSHOTS_DIR / f"{args.date}_snapshot.csv"
    )
    out_path = Path(args.out) if args.out else snap_path
    cohort_df = pd.read_csv(snap_path)
    projected = project_dataframe(cohort_df)
    projected.to_csv(out_path, index=False)
    print(f"Wrote {len(projected)} projected rows to {out_path}")


if __name__ == "__main__":
    main()
