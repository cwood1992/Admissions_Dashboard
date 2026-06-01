"""Rep pipeline health metrics.

Reads the raw CCS exports for a snapshot date and computes per-rep aggregates
across ALL cohorts (cancel rate, WBH rate, 60-day durability, composite quality
score). Output is the rep-level scorecard consumed by the dashboard Reps tab.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import utils
from scripts.ingest import _str_series

DURABILITY_WINDOW_DAYS = 60
# Placeholder threshold for "new rep" until calibration provides cohort-cycle history.
NEW_REP_PIPELINE_THRESHOLD = 30

# Durability and cancel_rate both need multi-week history (compare this week's
# roster to a prior snapshot). Sentinel until that history exists.
DURABILITY_UNAVAILABLE_SENTINEL = -1.0
CANCEL_RATE_UNAVAILABLE_SENTINEL = -1.0


@dataclass(frozen=True)
class RepHealthScorecard:
    rep_name: str
    total_assigned: int
    currently_enrolled: int
    cancelled: int
    cancel_rate: float
    wbh_rate: float
    durability: float  # NaN-safe: -1.0 sentinel if no 60d cohort
    durability_basis_count: int  # number of students in the 60d window
    quality_score: float  # raw composite in [0, 1]
    vs_team_avg: float  # quality_score / team_avg * 100, or 100.0 if no team avg
    is_new_rep: bool
    note: str = ""


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce either input schema to a canonical rep-health frame.

    Canonical columns: rep, sid, enrolled (bool), wbh/vip/p_fa/p_va/p_acc/p_adm.
    Detects EnrollList (has 'Current Cohort') vs per-cohort CCS ('CCS Status').
    """
    from scripts.ingest import _parse_action_flags, _parse_action_flags_el

    canonical_cols = ["rep", "sid", "enrolled", "wbh", "vip", "p_fa", "p_va", "p_acc", "p_adm"]
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=canonical_cols)
    if {"rep", "sid", "enrolled"}.issubset(df.columns):
        return df.reset_index(drop=True)  # already canonical (idempotent)

    is_enroll_list = utils.ENROLL_LIST_COLUMNS["cohort"] in df.columns
    if is_enroll_list:
        rep = df[utils.ENROLL_LIST_COLUMNS["rep_name"]].astype("string").fillna("").str.strip()
        sid = df[utils.ENROLL_LIST_COLUMNS["student_id"]].astype("string").fillna("").str.strip()
        enrolled = pd.Series(True, index=df.index)  # every EnrollList row is enrolled
        flags = _parse_action_flags_el(df)
    else:
        rep = df[utils.CCS_COLUMNS["rep_name"]].astype("string").fillna("").str.strip()
        sid = df[utils.CCS_COLUMNS["student_id"]].astype("string").fillna("").str.strip()
        status = df[utils.CCS_COLUMNS["enrollment_status"]].astype("string").fillna("").str.strip()
        enrolled = status == utils.ENROLLMENT_STATUS_ENROLLED
        flags = _parse_action_flags(df)

    out = pd.DataFrame({"rep": rep, "sid": sid, "enrolled": enrolled})
    for c in ["wbh", "vip", "p_fa", "p_va", "p_acc", "p_adm"]:
        out[c] = flags[c].values
    return out.reset_index(drop=True)


def _load_all_rows(raw_dir: Path, snapshot_date: date) -> pd.DataFrame:
    """Load + normalize the snapshot's enrollment rows (either format)."""
    enroll_list = raw_dir / utils.ENROLL_LIST_FILENAME
    if enroll_list.exists():
        df = utils.load_enroll_list(enroll_list)
        if len(df) == 0:
            raise FileNotFoundError(f"EnrollList in {raw_dir} has no rows")
        return _normalize(df)

    frames = []
    for csv_path in sorted(raw_dir.glob("*.csv")):
        if csv_path.name == utils.ENROLL_LIST_FILENAME:
            continue
        df = utils.load_ccs_csv(csv_path)
        if len(df) == 0:
            continue
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No enrollment rows found in {raw_dir}")
    return _normalize(pd.concat(frames, ignore_index=True))


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return float(num) / float(den) if den else default


def compute_rep_scorecards(
    rows: pd.DataFrame,
    snapshot_date: date,
    durability_window_days: int = DURABILITY_WINDOW_DAYS,
    new_rep_threshold: int = NEW_REP_PIPELINE_THRESHOLD,
    prior_snapshot_rows: pd.DataFrame | None = None,
) -> list[RepHealthScorecard]:
    """Compute per-rep scorecards from a row-level enrollment frame.

    `rows` may be raw (either schema) or already-canonical; it's normalized
    internally. `prior_snapshot_rows`, if provided, enables both 60-day
    durability and cancel_rate (both are week-over-week derivations — the
    EnrollList format has no in-snapshot cancellation signal).

    cancel_rate caveat: "cancelled" = on the rep's prior roster but absent from
    the *entire* current snapshot. Internal cohort/rep moves don't count
    (student is still somewhere); true departures and to-a-later-cohort drops do.
    """
    rows = _normalize(rows)
    prior = _normalize(prior_snapshot_rows) if prior_snapshot_rows is not None else None
    have_history = prior is not None and len(prior) > 0

    rep_series = rows["rep"] if len(rows) else pd.Series(dtype="string")
    is_enrolled = rows["enrolled"] if len(rows) else pd.Series(dtype=bool)

    current_all_sids = set(rows["sid"]) if len(rows) else set()
    if have_history:
        prior_sid_set = set(prior["sid"])
    else:
        prior_sid_set = set()
    in_window_mask = (
        rows["sid"].isin(prior_sid_set) if (have_history and len(rows)) else pd.Series(False, index=rows.index)
    )

    cards: list[RepHealthScorecard] = []
    for rep_name in sorted(r for r in rep_series.unique() if r):
        mask = rep_series == rep_name
        total = int(mask.sum())
        enrolled = int((mask & is_enrolled).sum())
        wbh = int((mask & is_enrolled & rows["wbh"]).sum())

        sixty_day_total = int((mask & in_window_mask).sum())
        sixty_day_still_enrolled = int((mask & in_window_mask & is_enrolled).sum())

        # Week-over-week cancel: prior roster for this rep, gone from snapshot.
        if have_history:
            prior_rep_sids = set(prior.loc[prior["rep"] == rep_name, "sid"])
            cancelled = sum(1 for s in prior_rep_sids if s not in current_all_sids)
            cancel_basis = len(prior_rep_sids)
            cancel_rate = _safe_div(cancelled, cancel_basis, default=0.0) if cancel_basis else 0.0
        else:
            cancelled = 0
            cancel_rate = CANCEL_RATE_UNAVAILABLE_SENTINEL

        wbh_rate = _safe_div(wbh, enrolled)
        if sixty_day_total > 0:
            durability = _safe_div(sixty_day_still_enrolled, sixty_day_total)
        else:
            durability = DURABILITY_UNAVAILABLE_SENTINEL
        is_new = total < new_rep_threshold

        terms = [wbh_rate]
        if cancel_rate >= 0:
            terms.append(max(0.0, 1.0 - cancel_rate))
        if durability >= 0:
            terms.append(durability)
        quality = sum(terms) / len(terms)

        if is_new:
            note = "new rep — excluded from team avg"
        elif not have_history:
            note = "cancel_rate & durability unavailable — needs prior snapshot history"
        elif sixty_day_total == 0:
            note = "no durability sample yet (no overlapping students vs prior)"
        else:
            note = ""

        cards.append(
            RepHealthScorecard(
                rep_name=rep_name,
                total_assigned=total,
                currently_enrolled=enrolled,
                cancelled=cancelled,
                cancel_rate=round(cancel_rate, 4) if cancel_rate >= 0 else cancel_rate,
                wbh_rate=round(wbh_rate, 4),
                durability=round(durability, 4) if durability >= 0 else durability,
                durability_basis_count=sixty_day_total,
                quality_score=round(quality, 4),
                vs_team_avg=0.0,  # filled below once team avg known
                is_new_rep=is_new,
                note=note,
            )
        )

    scoring_pool = [c for c in cards if not c.is_new_rep]
    team_avg = (
        sum(c.quality_score for c in scoring_pool) / len(scoring_pool)
        if scoring_pool
        else 0.0
    )

    return [
        RepHealthScorecard(
            rep_name=c.rep_name,
            total_assigned=c.total_assigned,
            currently_enrolled=c.currently_enrolled,
            cancelled=c.cancelled,
            cancel_rate=c.cancel_rate,
            wbh_rate=c.wbh_rate,
            durability=c.durability,
            durability_basis_count=c.durability_basis_count,
            quality_score=c.quality_score,
            vs_team_avg=round(
                (c.quality_score / team_avg * 100) if (team_avg > 0 and not c.is_new_rep) else 100.0,
                1,
            ),
            is_new_rep=c.is_new_rep,
            note=c.note,
        )
        for c in cards
    ]


def build_scorecards_from_raw(
    snapshot_date: str | date,
    raw_dir: Path | None = None,
    prior_raw_dir: Path | None = None,
) -> list[RepHealthScorecard]:
    snapshot_date = utils.parse_snapshot_date(snapshot_date)
    raw_dir = raw_dir or utils.snapshot_dir_for(snapshot_date)
    rows = _load_all_rows(raw_dir, snapshot_date)
    prior_rows = None
    if prior_raw_dir is not None and prior_raw_dir.exists():
        try:
            prior_rows = _load_all_rows(prior_raw_dir, snapshot_date)
        except FileNotFoundError:
            prior_rows = None
    return compute_rep_scorecards(rows, snapshot_date, prior_snapshot_rows=prior_rows)


def scorecards_to_dicts(cards: list[RepHealthScorecard]) -> list[dict]:
    return [asdict(c) for c in cards]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute rep pipeline health scorecards.")
    parser.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="JSON output path (defaults to dashboard/data/rep_health.json).",
    )
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    cards = build_scorecards_from_raw(args.date, raw_dir)

    out = Path(args.out) if args.out else utils.DASHBOARD_DATA_DIR / "rep_health.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "snapshot_date": str(args.date),
                "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "reps": scorecards_to_dicts(cards),
            },
            indent=2,
        )
    )
    js_out = out.with_suffix(".js")
    js_out.write_text(f"window.REP_HEALTH = {out.read_text()};\n")
    print(f"Wrote {len(cards)} rep scorecards to {out}")


if __name__ == "__main__":
    main()
