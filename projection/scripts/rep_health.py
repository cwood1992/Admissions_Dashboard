"""Rep pipeline health metrics (EnrollList-native, 2026-09 rework).

The weekly EnrollList has no cancellation signal and still lists students who
are sitting in classes that already started. So every metric here is built on
two rules:

1. **Forward roster only.** A rep's pipeline is their students in cohorts that
   have not started as of the snapshot (same window the cohort ingest uses).
2. **Outcome-based retention.** "Gone from the list" is not a cancel: students
   who start also leave it. A prior roster (the snapshot nearest N days back)
   is classified student-by-student against today's list and the booked CCS:

   - ``retained``     still enrolled in a cohort that has not started
   - ``started``      Active in a booked-class CCS (``raw/booked/``)
   - ``pending``      still listed in a class that started < 14 days ago
                      (most savable enrollments transfer by class-start week;
                      excluded from the denominator until that window closes)
   - ``lost_listed``  still listed in a class that started 14+ days ago
   - ``unknown``      gone, their class has started, but its booked CCS is not
                      staged yet, so a start cannot be ruled out (excluded)
   - ``gone``         off the list and not a start

   durability = (retained + started) / (retained + started + lost_listed + gone)

Tier progress (WBH / any-tag rate) is measured only inside the commitment
window (cohorts <= 45 days out): pooled history shows WBH tagging is 0% beyond
60 days, so a pipeline-wide rate compares reps on students nobody can tag yet.

Only aggregates leave this module (FERPA). Student IDs are used for the joins
and never written out.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from scripts import utils

COMMITMENT_WINDOW_DAYS = 45      # tier progress is measured on cohorts this close
DURABILITY_LOOKBACK_DAYS = 60    # spec: "students enrolled 60+ days ago"
LOSS_LOOKBACK_DAYS = 28          # shorter-horizon loss rate, same classification
LOOKBACK_TOLERANCE_DAYS = 10     # nearest snapshot must be within this of target
STALE_LOST_AFTER_DAYS = 14       # listed in a started class this long = lost
MIN_METRIC_SAMPLE = 10           # below this n a rate is shown but not scored
# Accounts that hold enrollments but are not admissions reps.
NON_REP_NAMES = frozenset({"House"})

OUTCOMES = ("retained", "started", "pending", "lost_listed", "unknown", "gone")
_DURABLE = ("retained", "started")
_LOST = ("lost_listed", "gone")

CANONICAL_COLS = ["rep", "sid", "cohort", "admission", "wbh", "tagged"]


@dataclass(frozen=True)
class RetentionMetric:
    """One prior-roster classification for one rep (or the team)."""

    n: int = 0                      # prior roster size
    basis: int = 0                  # denominator: n minus pending and unknown
    rate: float | None = None       # durable share of `basis`; None if basis == 0
    outcomes: dict[str, int] = field(default_factory=lambda: {o: 0 for o in OUTCOMES})


@dataclass(frozen=True)
class RepHealthScorecard:
    rep_name: str
    forward_enrolled: int           # students in cohorts not yet started
    near_enrolled: int              # ...of which within the commitment window
    wbh_near: int
    wbh_rate_near: float | None
    tagged_near: int                # any WBH / VIP / priority tag
    tagged_rate_near: float | None
    durability: RetentionMetric     # 60-day lookback
    retention_28d: RetentionMetric  # 28-day lookback (loss rate = 1 - rate)
    loss_rate_28d: float | None
    quality_score: float | None     # mean of the raw scored terms
    vs_team_avg: float | None       # mean of per-term (rep / team * 100)
    terms_used: list[str]
    note: str = ""


# --- loading / normalizing ---------------------------------------------------


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame:
    """Reduce either input schema to currently-enrolled canonical rows."""
    from scripts.ingest import _parse_action_flags, _parse_action_flags_el

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=CANONICAL_COLS)
    if set(CANONICAL_COLS).issubset(df.columns):
        return df.reset_index(drop=True)

    def _s(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series([""] * len(df), index=df.index, dtype="string")
        return df[col].astype("string").fillna("").str.strip()

    if utils.ENROLL_LIST_COLUMNS["rep_name"] in df.columns:
        c = utils.ENROLL_LIST_COLUMNS
        flags = _parse_action_flags_el(df)
        keep = pd.Series(True, index=df.index)  # every EnrollList row is enrolled
        cohort, admission = _s(c["cohort"]), _s(c["admission_type"])
    else:
        c = utils.CCS_COLUMNS
        flags = _parse_action_flags(df)
        keep = _s(c["enrollment_status"]) == utils.ENROLLMENT_STATUS_ENROLLED
        cohort, admission = _s(c["cohort"]), _s(c["enrollment_type"])

    out = pd.DataFrame(
        {
            "rep": _s(c["rep_name"]),
            "sid": _s(c["student_id"]),
            "cohort": cohort,
            "admission": admission.str.upper(),
            "wbh": flags["wbh"].values,
            "tagged": flags.any(axis=1).values,
        },
        index=df.index,
    )
    return out[keep].reset_index(drop=True)


def _load_all_rows(raw_dir: Path) -> pd.DataFrame:
    """Load + normalize a snapshot dir's enrollment rows (either format)."""
    enroll_list = raw_dir / utils.ENROLL_LIST_FILENAME
    if enroll_list.exists():
        df = utils.load_enroll_list(enroll_list)
        if len(df) == 0:
            raise FileNotFoundError(f"EnrollList in {raw_dir} has no rows")
        return _normalize(df)
    frames = [utils.load_ccs_csv(p) for p in sorted(raw_dir.glob("*.csv"))]
    frames = [f for f in frames if len(f)]
    if not frames:
        raise FileNotFoundError(f"No enrollment rows found in {raw_dir}")
    return _normalize(pd.concat(frames, ignore_index=True))


def load_started_ids(booked_dir: Path | None) -> tuple[set[str], set[str]]:
    """(student IDs that started, cohorts whose booked CCS is staged).

    A start is CCS Status == Active in that booked file. Sets dedupe the
    exact-duplicate rows booked exports sometimes carry.
    """
    started: set[str] = set()
    cohorts: set[str] = set()
    if booked_dir is None or not booked_dir.exists():
        return started, cohorts
    k = utils.CCS_COLUMNS
    for path in sorted(booked_dir.glob("CCS-*.csv")):
        df = utils.load_ccs_csv(path)
        if len(df) == 0:
            continue
        status = df[k["enrollment_status"]].astype("string").fillna("").str.strip()
        sid = df[k["student_id"]].astype("string").fillna("").str.strip()
        cohorts.update(c for c in df[k["cohort"]].astype("string").fillna("").str.strip().unique() if c)
        started.update(s for s in sid[status == utils.ENROLLMENT_STATUS_ACTIVE] if s)
    return started, cohorts


def pick_lookback_dir(
    raw_root: Path,
    as_of: date,
    target_days: int,
    tolerance_days: int = LOOKBACK_TOLERANCE_DAYS,
) -> tuple[date, Path] | None:
    """EnrollList snapshot dir nearest to `as_of - target_days`, within tolerance."""
    if not raw_root.exists():
        return None
    target = as_of - timedelta(days=target_days)
    best: tuple[int, date, Path] | None = None
    for p in raw_root.iterdir():
        if not p.is_dir() or not (p / utils.ENROLL_LIST_FILENAME).exists():
            continue
        try:
            d = utils.parse_snapshot_date(p.name)
        except ValueError:
            continue
        gap = abs((d - target).days)
        if d < as_of and gap <= tolerance_days and (best is None or gap < best[0]):
            best = (gap, d, p)
    return (best[1], best[2]) if best else None


# --- cohort timing -----------------------------------------------------------


def _cohort_number(cohort: str) -> int | None:
    digits = "".join(ch for ch in str(cohort) if ch.isdigit())
    return int(digits) if digits else None


def _days_since_start(cohort: str, as_of: date, start_dates: dict[str, date]) -> int | None:
    """Days since the cohort started as of `as_of`; negative/zero-or-less means
    not started (start day itself counts as not started, matching ingest).
    Returns None when the cohort is beyond the start-date table (treated as
    future); cohorts older than the table count as long started."""
    start = start_dates.get(cohort)
    if start is not None:
        return (as_of - start).days
    num = _cohort_number(cohort)
    known = [n for n in (_cohort_number(c) for c in start_dates) if n is not None]
    if num is not None and known and num > max(known):
        return None
    return 10**6


def forward_roster(rows: pd.DataFrame, as_of: date, start_dates: dict[str, date]) -> pd.DataFrame:
    """A snapshot's students in dated cohorts that have not started, one row
    per student, real reps only. REENROLLs are excluded, matching the cohort
    ingest, so the scorecard sums tie to the cohort table."""
    rows = _normalize(rows)
    if len(rows) == 0:
        return rows
    starts = rows["cohort"].map(start_dates)
    future = starts.apply(lambda s: isinstance(s, date) and s >= as_of)
    keep = (
        future
        & (rows["rep"] != "")
        & ~rows["rep"].isin(NON_REP_NAMES)
        & (rows["admission"] != utils.ENROLLMENT_TYPE_REENROLL)
    )
    out = rows[keep].drop_duplicates("sid").reset_index(drop=True)
    out["days_to_start"] = [(start_dates[c] - as_of).days for c in out["cohort"]]
    return out


# --- retention classification ------------------------------------------------


def classify_outcomes(
    prior_roster: pd.DataFrame,
    current_rows: pd.DataFrame,
    as_of: date,
    start_dates: dict[str, date],
    started_ids: set[str],
    booked_cohorts: set[str],
    stale_lost_after_days: int = STALE_LOST_AFTER_DAYS,
) -> pd.Series:
    """Outcome label per prior-roster student as of `as_of` (see module doc)."""
    current = _normalize(current_rows)
    listed: dict[str, int | None] = {}  # sid -> days since their listed cohort started
    for sid, cohort in zip(current["sid"], current["cohort"]):
        since = _days_since_start(cohort, as_of, start_dates)
        # A student listed twice keeps their most-future listing.
        if sid not in listed or since is None or (listed[sid] is not None and since < listed[sid]):
            listed[sid] = since

    def _one(sid: str, prior_cohort: str) -> str:
        if sid in listed and (listed[sid] is None or listed[sid] <= 0):
            return "retained"
        if sid in started_ids:
            return "started"
        if sid in listed:
            return "pending" if listed[sid] < stale_lost_after_days else "lost_listed"
        since = _days_since_start(prior_cohort, as_of, start_dates)
        if since is not None and since > 0 and prior_cohort not in booked_cohorts:
            return "unknown"
        return "gone"

    return pd.Series(
        [_one(s, c) for s, c in zip(prior_roster["sid"], prior_roster["cohort"])],
        index=prior_roster.index,
        dtype="object",
    )


def _retention(outcomes: pd.Series) -> RetentionMetric:
    counts = {o: int((outcomes == o).sum()) for o in OUTCOMES}
    durable = sum(counts[o] for o in _DURABLE)
    basis = durable + sum(counts[o] for o in _LOST)
    return RetentionMetric(
        n=int(len(outcomes)),
        basis=basis,
        rate=round(durable / basis, 4) if basis else None,
        outcomes=counts,
    )


def _retention_by_rep(
    prior: tuple[date, pd.DataFrame] | None,
    current_rows: pd.DataFrame,
    as_of: date,
    start_dates: dict[str, date],
    started_ids: set[str],
    booked_cohorts: set[str],
) -> tuple[dict[str, RetentionMetric], RetentionMetric]:
    if prior is None:
        return {}, RetentionMetric()
    prior_date, prior_rows = prior
    roster = forward_roster(prior_rows, prior_date, start_dates)
    if len(roster) == 0:
        return {}, RetentionMetric()
    outcomes = classify_outcomes(roster, current_rows, as_of, start_dates, started_ids, booked_cohorts)
    by_rep = {rep: _retention(outcomes[roster["rep"] == rep]) for rep in sorted(roster["rep"].unique())}
    return by_rep, _retention(outcomes)


# --- scorecards --------------------------------------------------------------


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def compute_rep_scorecards(
    rows: pd.DataFrame,
    snapshot_date: str | date,
    *,
    start_dates: dict[str, date] | None = None,
    durability_prior: tuple[date, pd.DataFrame] | None = None,
    loss_prior: tuple[date, pd.DataFrame] | None = None,
    started_ids: set[str] | None = None,
    booked_cohorts: set[str] | None = None,
    commitment_window_days: int = COMMITMENT_WINDOW_DAYS,
    min_sample: int = MIN_METRIC_SAMPLE,
) -> dict:
    """Build the rep-health payload: ``{"params", "team", "reps"}``.

    `rows` is the current snapshot (raw either-schema or canonical).
    `durability_prior` / `loss_prior` are ``(snapshot_date, rows)`` for the
    lookback snapshots; without them the retention terms are unavailable.
    """
    from scripts.ingest import load_program_start_dates

    as_of = utils.parse_snapshot_date(snapshot_date)
    start_dates = start_dates if start_dates is not None else load_program_start_dates()
    started_ids = started_ids or set()
    booked_cohorts = booked_cohorts or set()
    current = _normalize(rows)
    roster = forward_roster(current, as_of, start_dates)
    near = roster[roster["days_to_start"] <= commitment_window_days] if len(roster) else roster

    dur_by_rep, dur_team = _retention_by_rep(
        durability_prior, current, as_of, start_dates, started_ids, booked_cohorts
    )
    loss_by_rep, loss_team = _retention_by_rep(
        loss_prior, current, as_of, start_dates, started_ids, booked_cohorts
    )

    team_terms = {
        "tagged_rate_near": _rate(int(near["tagged"].sum()), len(near)) if len(near) else None,
        "durability_60d": dur_team.rate,
        "retention_28d": loss_team.rate,
    }

    rep_names = sorted(set(roster["rep"]) | set(dur_by_rep) | set(loss_by_rep))
    cards: list[RepHealthScorecard] = []
    for rep in rep_names:
        mine = roster[roster["rep"] == rep]
        mine_near = near[near["rep"] == rep]
        dur = dur_by_rep.get(rep, RetentionMetric())
        ret = loss_by_rep.get(rep, RetentionMetric())
        n_near = len(mine_near)

        # (value, sample size) per scored term; a term is scored only when the
        # rep has a big enough sample and the team has a nonzero rate to index to.
        terms = {
            "tagged_rate_near": (_rate(int(mine_near["tagged"].sum()), n_near), n_near),
            "durability_60d": (dur.rate, dur.basis),
            "retention_28d": (ret.rate, ret.basis),
        }
        used, indices, raws, thin = [], [], [], []
        for name, (value, n) in terms.items():
            team_value = team_terms[name]
            if value is None or not team_value:
                continue
            if n < min_sample:
                thin.append(f"{name} n={n}")
                continue
            used.append(name)
            raws.append(value)
            indices.append(value / team_value * 100)

        notes = []
        if thin:
            notes.append(f"not scored (n<{min_sample}): " + ", ".join(thin))
        if durability_prior is None:
            notes.append("no snapshot near 60 days back")
        if loss_prior is None:
            notes.append("no snapshot near 28 days back")

        cards.append(
            RepHealthScorecard(
                rep_name=rep,
                forward_enrolled=len(mine),
                near_enrolled=n_near,
                wbh_near=int(mine_near["wbh"].sum()),
                wbh_rate_near=_rate(int(mine_near["wbh"].sum()), n_near),
                tagged_near=int(mine_near["tagged"].sum()),
                tagged_rate_near=terms["tagged_rate_near"][0],
                durability=dur,
                retention_28d=ret,
                loss_rate_28d=round(1 - ret.rate, 4) if ret.rate is not None else None,
                quality_score=round(sum(raws) / len(raws), 4) if raws else None,
                vs_team_avg=round(sum(indices) / len(indices), 1) if indices else None,
                terms_used=used,
                note="; ".join(notes),
            )
        )

    return {
        "params": {
            "commitment_window_days": commitment_window_days,
            "stale_lost_after_days": STALE_LOST_AFTER_DAYS,
            "min_metric_sample": min_sample,
            "durability_target_days": DURABILITY_LOOKBACK_DAYS,
            "durability_prior_date": durability_prior[0].isoformat() if durability_prior else None,
            "loss_target_days": LOSS_LOOKBACK_DAYS,
            "loss_prior_date": loss_prior[0].isoformat() if loss_prior else None,
            "booked_cohorts": sorted(booked_cohorts),
            "excluded_names": sorted(NON_REP_NAMES),
        },
        "team": {
            "forward_enrolled": len(roster),
            "near_enrolled": len(near),
            "wbh_near": int(near["wbh"].sum()) if len(near) else 0,
            "wbh_rate_near": _rate(int(near["wbh"].sum()), len(near)) if len(near) else None,
            "tagged_near": int(near["tagged"].sum()) if len(near) else 0,
            "tagged_rate_near": team_terms["tagged_rate_near"],
            "durability": asdict(dur_team),
            "retention_28d": asdict(loss_team),
            "loss_rate_28d": round(1 - loss_team.rate, 4) if loss_team.rate is not None else None,
        },
        "reps": [asdict(c) for c in cards],
    }


def build_payload_from_raw(
    snapshot_date: str | date,
    raw_dir: Path | None = None,
    raw_root: Path | None = None,
    booked_dir: Path | None = None,
    start_dates: dict[str, date] | None = None,
) -> dict:
    """Load the snapshot, its two lookback snapshots and the booked CCS, then score."""
    as_of = utils.parse_snapshot_date(snapshot_date)
    raw_dir = raw_dir or utils.snapshot_dir_for(as_of)
    raw_root = raw_root or raw_dir.parent
    booked_dir = booked_dir or raw_root / "booked"
    rows = _load_all_rows(raw_dir)

    def _prior(target_days: int) -> tuple[date, pd.DataFrame] | None:
        found = pick_lookback_dir(raw_root, as_of, target_days)
        if found is None:
            return None
        try:
            return found[0], _load_all_rows(found[1])
        except FileNotFoundError:
            return None

    started_ids, booked_cohorts = load_started_ids(booked_dir)
    return compute_rep_scorecards(
        rows,
        as_of,
        start_dates=start_dates,
        durability_prior=_prior(DURABILITY_LOOKBACK_DAYS),
        loss_prior=_prior(LOSS_LOOKBACK_DAYS),
        started_ids=started_ids,
        booked_cohorts=booked_cohorts,
    )


def write_payload(payload: dict, snapshot_date: str | date, out: Path | None = None) -> Path:
    out = out or utils.DASHBOARD_DATA_DIR / "rep_health.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    full = {
        "snapshot_date": str(snapshot_date),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        **payload,
    }
    text = json.dumps(full, indent=2)
    out.write_text(text, encoding="utf-8")
    out.with_suffix(".js").write_text(f"window.REP_HEALTH = {text};\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute rep pipeline health scorecards.")
    parser.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--out", default=None, help="JSON output path (default dashboard/data/rep_health.json).")
    args = parser.parse_args()

    payload = build_payload_from_raw(args.date, Path(args.raw_dir) if args.raw_dir else None)
    out = write_payload(payload, args.date, Path(args.out) if args.out else None)
    print(f"Wrote {len(payload['reps'])} rep scorecards to {out}")


if __name__ == "__main__":
    main()
