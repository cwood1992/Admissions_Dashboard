"""Ingest weekly enrollment exports into aggregated per-cohort + per-rep snapshots.

Two input formats are supported:

1. EnrollList.csv (consolidated, new weekly source, 2026-05-15+):
   One file, all currently-enrolled-in-a-future-cohort students. Grouped by
   `Current Cohort`. Cancelled-gone students are absent; cancelled-moved-later
   appear under their new cohort with Admission Type=TRANSFER + Previous Cohort.
   `Current Enroll Date` enables cold-vs-new-untagged and snapshot-derived
   metrics. This is auto-detected: if raw/<date>/EnrollList.csv exists it wins.

2. Per-cohort CCS (old format, retained as the booked-class calibration
   source): 4–5 metadata lines + header "Enroll Type", ..., one file per
   cohort. Transfer chain via CCS Status=Cancel + NEXT Cohort.

Start dates come from baselines/program_start_dates_2026.csv either way.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import utils


@dataclass
class RepBreakdown:
    rep_name: str
    rep_total_assigned: int
    rep_currently_enrolled: int
    rep_new: int
    rep_transfer: int
    rep_cancelled: int
    rep_cancel_rate: float
    rep_wbh: int
    rep_vip: int
    rep_priority: int


@dataclass
class CohortSnapshot:
    snapshot_date: date
    cohort: str
    program: str
    start_date: date | None
    days_to_start: int | None

    currently_enrolled: int
    new_enrolled: int
    transfer_enrolled: int
    reenroll_enrolled: int

    wbh_count: int
    vip_count: int

    p_fa_count: int
    p_va_count: int
    p_acc_count: int
    p_adm_count: int

    untagged_count: int

    # EnrollList-only (None when ingested from old per-cohort CCS).
    cold_count: int | None = None
    new_untagged_count: int | None = None
    transferred_in_count: int | None = None
    weekly_velocity: int | None = None  # rows enrolled within the last 7 days

    # Old per-cohort-CCS-only (None when ingested from EnrollList).
    total_ever_enrolled: int | None = None
    cancelled_total: int | None = None
    cancelled_gone: int | None = None
    cancelled_moved_later: int | None = None

    reps: list[RepBreakdown] = field(default_factory=list)


def _col(df: pd.DataFrame, key: str) -> pd.Series:
    return df[utils.CCS_COLUMNS[key]]


def _str_series(df: pd.DataFrame, key: str) -> pd.Series:
    return _col(df, key).astype("string").fillna("").str.strip()


def load_program_start_dates(path: Path | None = None) -> dict[str, date]:
    """Load the per-cohort start-date lookup.

    The on-disk file is keyed by cohort *number* (10 rows per year) because all
    programs at the same batch number share a single start date. This function
    expands into a {cohort_code: date} dict by fanning out each cohort number
    to its UDT/NDT-Day/NDT-Night codes (NC only at even-numbered cohorts).
    """
    path = path or utils.BASELINES_DIR / "program_start_dates_2026.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out: dict[str, date] = {}
    for _, row in df.iterrows():
        try:
            d = pd.to_datetime(row["start_date"]).date()
        except Exception:
            continue
        # Legacy schema: per-cohort row with 'cohort' column.
        if "cohort" in df.columns and pd.notna(row.get("cohort", None)):
            out[str(row["cohort"])] = d
            continue
        # New schema: keyed by cohort_number, expand to UDT/NDT/(NC if even).
        try:
            num = int(row["cohort_number"])
        except (KeyError, ValueError, TypeError):
            continue
        out[f"UDT{num}"] = d
        out[f"NDT{num}"] = d
        if num % 2 == 0:
            out[f"NDT{num}NC"] = d
    return out


def _parse_action_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a DataFrame of boolean columns mirroring parse_action_status output."""
    raw = _str_series(df, "action_status")
    parsed = raw.apply(utils.parse_action_status)
    return pd.DataFrame(
        {
            "wbh": parsed.apply(lambda d: bool(d["wbh"])),
            "vip": parsed.apply(lambda d: bool(d["vip"])),
            "p_fa": parsed.apply(lambda d: bool(d["p_fa"])),
            "p_va": parsed.apply(lambda d: bool(d["p_va"])),
            "p_acc": parsed.apply(lambda d: bool(d["p_acc"])),
            "p_adm": parsed.apply(lambda d: bool(d["p_adm"])),
        }
    )


def _per_rep_breakdown(
    df: pd.DataFrame,
    is_enrolled: pd.Series,
    is_cancelled: pd.Series,
    enroll_type: pd.Series,
    flags: pd.DataFrame,
) -> list[RepBreakdown]:
    rep_series = _str_series(df, "rep_name")
    any_priority = flags[["p_fa", "p_va", "p_acc", "p_adm"]].any(axis=1)
    reps: list[RepBreakdown] = []
    for rep_name in sorted(r for r in rep_series.unique() if r):
        mask = rep_series == rep_name
        total = int(mask.sum())
        cancelled = int((mask & is_cancelled).sum())
        reps.append(
            RepBreakdown(
                rep_name=rep_name,
                rep_total_assigned=total,
                rep_currently_enrolled=int((mask & is_enrolled).sum()),
                rep_new=int(
                    (mask & is_enrolled & (enroll_type == utils.ENROLLMENT_TYPE_NEW)).sum()
                ),
                rep_transfer=int(
                    (mask & is_enrolled & (enroll_type == utils.ENROLLMENT_TYPE_TRANSFER)).sum()
                ),
                rep_cancelled=cancelled,
                rep_cancel_rate=round(cancelled / total, 4) if total else 0.0,
                rep_wbh=int((mask & is_enrolled & flags["wbh"]).sum()),
                rep_vip=int((mask & is_enrolled & flags["vip"]).sum()),
                rep_priority=int((mask & is_enrolled & any_priority).sum()),
            )
        )
    return reps


def ingest_cohort_csv(
    path: Path,
    snapshot_date: str | date,
    start_dates: dict[str, date] | None = None,
) -> CohortSnapshot:
    snapshot_date = utils.parse_snapshot_date(snapshot_date)
    df = utils.load_ccs_csv(path)

    # Derive cohort code from the data when possible; fall back to filename
    # parsing for empty cohorts (no data rows).
    cohort_col = _str_series(df, "cohort") if len(df) > 0 else pd.Series([], dtype=str)
    if len(cohort_col) and cohort_col.iloc[0]:
        cohort = cohort_col.iloc[0]
    else:
        cohort = utils.cohort_from_filename(path)
    program = utils.program_for_cohort(cohort)

    if start_dates is None:
        start_dates = load_program_start_dates()
    start_date = start_dates.get(cohort)
    days_to_start = (start_date - snapshot_date).days if start_date else None

    status = _str_series(df, "enrollment_status")
    enroll_type = _str_series(df, "enrollment_type")
    next_cohort = _str_series(df, "next_cohort")
    flags = _parse_action_flags(df) if len(df) else pd.DataFrame(
        {k: pd.Series(dtype=bool) for k in ["wbh", "vip", "p_fa", "p_va", "p_acc", "p_adm"]}
    )

    is_enrolled = status == utils.ENROLLMENT_STATUS_ENROLLED
    is_cancelled = status == utils.ENROLLMENT_STATUS_CANCELLED

    any_tier_or_priority = (
        flags["wbh"] | flags["vip"] | flags["p_fa"] | flags["p_va"] | flags["p_acc"] | flags["p_adm"]
    )

    snap = CohortSnapshot(
        snapshot_date=snapshot_date,
        cohort=cohort,
        program=program,
        start_date=start_date,
        days_to_start=days_to_start,
        total_ever_enrolled=int(len(df)),
        currently_enrolled=int(is_enrolled.sum()),
        new_enrolled=int((is_enrolled & (enroll_type == utils.ENROLLMENT_TYPE_NEW)).sum()),
        transfer_enrolled=int(
            (is_enrolled & (enroll_type == utils.ENROLLMENT_TYPE_TRANSFER)).sum()
        ),
        reenroll_enrolled=int(
            (is_enrolled & (enroll_type == utils.ENROLLMENT_TYPE_REENROLL)).sum()
        ),
        cancelled_total=int(is_cancelled.sum()),
        cancelled_gone=int((is_cancelled & (next_cohort == "")).sum()),
        cancelled_moved_later=int((is_cancelled & (next_cohort != "")).sum()),
        wbh_count=int((is_enrolled & flags["wbh"]).sum()),
        vip_count=int((is_enrolled & flags["vip"]).sum()),
        p_fa_count=int((is_enrolled & flags["p_fa"]).sum()),
        p_va_count=int((is_enrolled & flags["p_va"]).sum()),
        p_acc_count=int((is_enrolled & flags["p_acc"]).sum()),
        p_adm_count=int((is_enrolled & flags["p_adm"]).sum()),
        untagged_count=int((is_enrolled & ~any_tier_or_priority).sum()),
        reps=_per_rep_breakdown(df, is_enrolled, is_cancelled, enroll_type, flags),
    )

    _validate_invariants(snap)
    return snap


def _validate_invariants(snap: CohortSnapshot) -> None:
    """Old-format (per-cohort CCS) invariants. EnrollList sets the old-only
    fields to None; those checks are skipped for it."""
    if snap.total_ever_enrolled is None:
        # EnrollList path: admission types can include values we don't classify,
        # so new+transfer+reenroll need not equal currently_enrolled. Per-rep
        # totals trivially sum to currently_enrolled. Nothing hard to assert.
        return
    enrolled_sum = snap.new_enrolled + snap.transfer_enrolled + snap.reenroll_enrolled
    if enrolled_sum != snap.currently_enrolled:
        raise ValueError(
            f"{snap.cohort}: new+transfer+reenroll ({enrolled_sum}) "
            f"!= currently_enrolled ({snap.currently_enrolled}). "
            "Check enrollment_type values against CCS_COLUMNS vocabulary."
        )
    cancel_sum = (snap.cancelled_gone or 0) + (snap.cancelled_moved_later or 0)
    if cancel_sum != snap.cancelled_total:
        raise ValueError(
            f"{snap.cohort}: cancelled_gone+cancelled_moved_later ({cancel_sum}) "
            f"!= cancelled_total ({snap.cancelled_total})."
        )
    if snap.reps:
        rep_total = sum(r.rep_total_assigned for r in snap.reps)
        if rep_total != snap.total_ever_enrolled:
            raise ValueError(
                f"{snap.cohort}: per-rep totals ({rep_total}) "
                f"!= total_ever_enrolled ({snap.total_ever_enrolled}). "
                "Likely missing rep_name on some rows."
            )


def snapshot_to_flat_dict(snap: CohortSnapshot) -> dict:
    d = asdict(snap)
    d.pop("reps", None)
    d["snapshot_date"] = snap.snapshot_date.isoformat()
    d["start_date"] = snap.start_date.isoformat() if snap.start_date else None
    return d


def reps_to_rows(snap: CohortSnapshot) -> list[dict]:
    rows: list[dict] = []
    for rep in snap.reps:
        row = asdict(rep)
        row["snapshot_date"] = snap.snapshot_date.isoformat()
        row["cohort"] = snap.cohort
        row["program"] = snap.program
        rows.append(row)
    return rows


class MissingCohortFilesError(ValueError):
    """Raised when the raw snapshot directory has the wrong program count."""


def _validate_snapshot_distribution(snapshots: list[CohortSnapshot]) -> None:
    by_program: dict[str, int] = {}
    for snap in snapshots:
        by_program[snap.program] = by_program.get(snap.program, 0) + 1
    discrepancies = []
    for program, expected in utils.EXPECTED_COHORT_COUNTS.items():
        actual = by_program.get(program, 0)
        if actual != expected:
            discrepancies.append(f"{program}: expected {expected}, got {actual}")
    unexpected = set(by_program) - set(utils.EXPECTED_COHORT_COUNTS)
    for program in sorted(unexpected):
        discrepancies.append(f"{program}: unexpected program ({by_program[program]} cohort(s))")
    if discrepancies:
        raise MissingCohortFilesError(
            "Cohort count does not match 10/10/5 expectation. "
            "Either files are missing or the program mix changed: "
            + "; ".join(discrepancies)
        )


# --- EnrollList (consolidated weekly source) --------------------------------


def _el_str(df: pd.DataFrame, key: str) -> pd.Series:
    col = utils.ENROLL_LIST_COLUMNS[key]
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[col].astype("string").fillna("").str.strip()


def _parse_action_flags_el(df: pd.DataFrame) -> pd.DataFrame:
    raw = _el_str(df, "action_status")
    parsed = raw.apply(utils.parse_action_status)
    return pd.DataFrame(
        {
            "wbh": parsed.apply(lambda d: bool(d["wbh"])),
            "vip": parsed.apply(lambda d: bool(d["vip"])),
            "p_fa": parsed.apply(lambda d: bool(d["p_fa"])),
            "p_va": parsed.apply(lambda d: bool(d["p_va"])),
            "p_acc": parsed.apply(lambda d: bool(d["p_acc"])),
            "p_adm": parsed.apply(lambda d: bool(d["p_adm"])),
        },
        index=df.index,
    )


def _el_rep_breakdown(group: pd.DataFrame, flags: pd.DataFrame) -> list[RepBreakdown]:
    rep_series = _el_str(group, "rep_name")
    admission = _el_str(group, "admission_type").str.upper()
    any_priority = flags[["p_fa", "p_va", "p_acc", "p_adm"]].any(axis=1)
    reps: list[RepBreakdown] = []
    for rep_name in sorted(r for r in rep_series.unique() if r):
        mask = rep_series == rep_name
        total = int(mask.sum())
        reps.append(
            RepBreakdown(
                rep_name=rep_name,
                rep_total_assigned=total,
                rep_currently_enrolled=total,  # every EnrollList row is enrolled
                rep_new=int((mask & (admission == utils.ENROLLMENT_TYPE_NEW)).sum()),
                rep_transfer=int((mask & (admission == utils.ENROLLMENT_TYPE_TRANSFER)).sum()),
                rep_cancelled=0,  # not in EnrollList; rep_health derives week-over-week
                rep_cancel_rate=0.0,
                rep_wbh=int((mask & flags["wbh"]).sum()),
                rep_vip=int((mask & flags["vip"]).sum()),
                rep_priority=int((mask & any_priority).sum()),
            )
        )
    return reps


def _el_cohort_snapshot(
    group: pd.DataFrame,
    cohort: str,
    snapshot_date: date,
    start_dates: dict[str, date],
) -> CohortSnapshot:
    program = utils.program_for_cohort(cohort)
    start_date = start_dates.get(cohort)
    days_to_start = (start_date - snapshot_date).days if start_date else None

    base = dict(
        snapshot_date=snapshot_date,
        cohort=cohort,
        program=program,
        start_date=start_date,
        days_to_start=days_to_start,
    )
    if len(group) == 0:
        return CohortSnapshot(
            **base,
            currently_enrolled=0,
            new_enrolled=0,
            transfer_enrolled=0,
            reenroll_enrolled=0,
            wbh_count=0,
            vip_count=0,
            p_fa_count=0,
            p_va_count=0,
            p_acc_count=0,
            p_adm_count=0,
            untagged_count=0,
            cold_count=0,
            new_untagged_count=0,
            transferred_in_count=0,
            weekly_velocity=0,
            reps=[],
        )

    # REENROLLs are previously-dropped students returning. They're not fresh
    # pipeline volume — drop them from every metric except the visibility count.
    admission_all = _el_str(group, "admission_type").str.upper()
    reenroll_count = int((admission_all == utils.ENROLLMENT_TYPE_REENROLL).sum())
    group = group[admission_all != utils.ENROLLMENT_TYPE_REENROLL].reset_index(drop=True)
    n = len(group)

    admission = _el_str(group, "admission_type").str.upper()
    flags = _parse_action_flags_el(group)
    prev_cohort = _el_str(group, "prev_cohort")
    enroll_dates = pd.to_datetime(_el_str(group, "current_enroll_date"), errors="coerce")
    days_enrolled = (pd.Timestamp(snapshot_date) - enroll_dates).dt.days

    any_tag = (
        flags["wbh"] | flags["vip"] | flags["p_fa"] | flags["p_va"] | flags["p_acc"] | flags["p_adm"]
    )
    untagged = ~any_tag
    # Unparseable enroll date -> treat as cold (around long enough to be stale/unknown).
    is_recent = (days_enrolled <= utils.UNTAGGED_COLD_THRESHOLD_DAYS).fillna(False)
    # Weekly velocity: students whose current-cohort enroll date is within the
    # last 7 days. Works off the snapshot alone (no prior week needed).
    enrolled_within_7d = (days_enrolled <= utils.VELOCITY_WINDOW_DAYS).fillna(False)

    return CohortSnapshot(
        **base,
        currently_enrolled=n,
        new_enrolled=int((admission == utils.ENROLLMENT_TYPE_NEW).sum()),
        transfer_enrolled=int((admission == utils.ENROLLMENT_TYPE_TRANSFER).sum()),
        reenroll_enrolled=reenroll_count,
        wbh_count=int(flags["wbh"].sum()),
        vip_count=int(flags["vip"].sum()),
        p_fa_count=int(flags["p_fa"].sum()),
        p_va_count=int(flags["p_va"].sum()),
        p_acc_count=int(flags["p_acc"].sum()),
        p_adm_count=int(flags["p_adm"].sum()),
        untagged_count=int(untagged.sum()),
        cold_count=int((untagged & ~is_recent).sum()),
        new_untagged_count=int((untagged & is_recent).sum()),
        transferred_in_count=int((prev_cohort != "").sum()),
        weekly_velocity=int(enrolled_within_7d.sum()),
        reps=_el_rep_breakdown(group, flags),
    )


def ingest_enroll_list(
    path: Path,
    snapshot_date: str | date,
    start_dates: dict[str, date] | None = None,
    *,
    strict: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshot_date = utils.parse_snapshot_date(snapshot_date)
    if start_dates is None:
        start_dates = load_program_start_dates()
    df = utils.load_enroll_list(path)

    cohort_series = _el_str(df, "cohort")
    present = sorted(c for c in cohort_series.unique() if c)

    # The "All Enrolled Students" export spans every cohort (already-started
    # and future). We only project the *future* window: cohorts in
    # program_start_dates whose start is still ahead of this snapshot. Cohorts
    # outside that window (started/historical, or numbers not in the baseline)
    # are expected and silently ignored — not an error.
    expected = {c for c, d in start_dates.items() if d >= snapshot_date}
    ignored = [c for c in present if c not in expected]
    if strict and ignored:
        print(
            f"  [ingest] {len(ignored)} out-of-window cohort(s) in EnrollList "
            f"ignored (started/historical or not in 2026 window), e.g. "
            f"{', '.join(ignored[:5])}{'...' if len(ignored) > 5 else ''}"
        )

    grouped = (
        {c: g for c, g in df.groupby(cohort_series)} if len(df) else {}
    )
    cohorts_to_emit = sorted(expected)

    snapshots: list[CohortSnapshot] = []
    empty = df.iloc[0:0]
    for cohort in cohorts_to_emit:
        group = grouped.get(cohort, empty)
        snapshots.append(_el_cohort_snapshot(group, cohort, snapshot_date, start_dates))

    cohort_rows = [snapshot_to_flat_dict(s) for s in snapshots]
    rep_rows: list[dict] = []
    for s in snapshots:
        rep_rows.extend(reps_to_rows(s))
    return pd.DataFrame(cohort_rows), pd.DataFrame(rep_rows)


def ingest_snapshot_dir(
    snapshot_date: str | date,
    raw_dir: Path | None = None,
    *,
    strict: bool = True,
    start_dates: dict[str, date] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshot_date = utils.parse_snapshot_date(snapshot_date)
    raw_dir = raw_dir or utils.snapshot_dir_for(snapshot_date)
    if not raw_dir.exists():
        raise FileNotFoundError(f"{raw_dir} does not exist")

    # New consolidated format wins if present.
    enroll_list = raw_dir / utils.ENROLL_LIST_FILENAME
    if enroll_list.exists():
        return ingest_enroll_list(
            enroll_list, snapshot_date, start_dates=start_dates, strict=strict
        )

    csv_paths = sorted(
        p for p in raw_dir.glob("*.csv") if p.name != utils.ENROLL_LIST_FILENAME
    )
    if not csv_paths:
        raise FileNotFoundError(f"No CCS CSVs found in {raw_dir}")

    if start_dates is None:
        start_dates = load_program_start_dates()

    snapshots: list[CohortSnapshot] = [
        ingest_cohort_csv(p, snapshot_date, start_dates) for p in csv_paths
    ]

    if strict:
        _validate_snapshot_distribution(snapshots)

    cohort_rows = [snapshot_to_flat_dict(s) for s in snapshots]
    rep_rows: list[dict] = []
    for s in snapshots:
        rep_rows.extend(reps_to_rows(s))

    return pd.DataFrame(cohort_rows), pd.DataFrame(rep_rows)


def write_snapshot_files(
    cohort_df: pd.DataFrame,
    rep_df: pd.DataFrame,
    snapshot_date: str | date,
    out_dir: Path | None = None,
) -> tuple[Path, Path]:
    snapshot_date = utils.parse_snapshot_date(snapshot_date)
    out_dir = out_dir or utils.SNAPSHOTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = out_dir / f"{snapshot_date.isoformat()}_snapshot.csv"
    rep_path = out_dir / f"{snapshot_date.isoformat()}_reps.csv"
    cohort_df.to_csv(cohort_path, index=False)
    rep_df.to_csv(rep_path, index=False)
    return cohort_path, rep_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CCS exports.")
    parser.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument(
        "--cohort",
        default=None,
        help="Cohort code or filename stem (e.g. UDT566 or CCS-U566). "
        "If omitted, ingests the full snapshot directory.",
    )
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir) if args.raw_dir else utils.snapshot_dir_for(args.date)

    if args.cohort:
        # Cohort can be given as UDT566 / NDT566 / NDT566NC, or as a filename.
        # Real CCS filenames use compressed prefixes: CCS-U566, CCS-N566, CCS-NNC566.
        coh = args.cohort
        num = "".join(c for c in coh if c.isdigit())
        candidates = [
            raw_dir / coh,
            raw_dir / f"{coh}.csv",
            raw_dir / f"CCS-{coh}.csv",
        ]
        if coh.startswith("UDT"):
            candidates.append(raw_dir / f"CCS-U{num}.csv")
        elif coh.endswith("NC"):
            candidates.append(raw_dir / f"CCS-NNC{num}.csv")
        elif coh.startswith("NDT"):
            candidates.append(raw_dir / f"CCS-N{num}.csv")
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            raise FileNotFoundError(f"No file matching {args.cohort!r} in {raw_dir}")
        snap = ingest_cohort_csv(path, args.date)
        flat = snapshot_to_flat_dict(snap)
        width = max(len(k) for k in flat)
        for k, v in flat.items():
            print(f"{k.ljust(width)}  {v}")
        print(f"\nReps ({len(snap.reps)}):")
        for r in snap.reps:
            print(
                f"  {r.rep_name}: assigned={r.rep_total_assigned}, "
                f"enrolled={r.rep_currently_enrolled}, "
                f"cancel_rate={r.rep_cancel_rate}"
            )
        return

    cohort_df, rep_df = ingest_snapshot_dir(args.date, raw_dir, strict=not args.no_strict)
    cohort_path, rep_path = write_snapshot_files(cohort_df, rep_df, args.date)
    print(f"Wrote {len(cohort_df)} cohort rows to {cohort_path}")
    print(f"Wrote {len(rep_df)} rep rows to {rep_path}")


if __name__ == "__main__":
    main()
