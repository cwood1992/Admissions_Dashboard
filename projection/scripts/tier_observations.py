"""Horizon-matched tier observations for calibration.

A tier rate is applied in the near and medium regimes (0 to FAR_REGIME_THRESHOLD
days before start), so it is measured over the same window: every stored
EnrollList in that window, each tagged student in it, matched by student ID
against the booked-class CCS's Active rows. Measuring only at start (about 3 days
out) understates VIP+Priority -- by then the eventual starters have become WBH --
and overstates WBH.

Tier flags are read from the pre-start EnrollLists, so Action Status being
cleared on show in the booked CCS cannot touch them.

FERPA: returns counts only. Student IDs stay inside this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import ingest, utils
from scripts.projections import FAR_REGIME_THRESHOLD

ENROLL_LIST_FILENAME = "EnrollList.csv"


@dataclass(frozen=True)
class TierObservation:
    """Student-snapshot pairs observed in the window and how many started.

    Pairs are not independent draws: a student present in five snapshots counts
    five times. Calibration uses the ratio as one observation per cohort.
    """

    snapshots_used: int
    wbh_obs_pairs: int
    wbh_obs_started: int
    vip_priority_obs_pairs: int
    vip_priority_obs_started: int

    def as_row(self) -> dict:
        return {
            "wbh_obs_pairs": self.wbh_obs_pairs,
            "wbh_obs_started": self.wbh_obs_started,
            "vip_priority_obs_pairs": self.vip_priority_obs_pairs,
            "vip_priority_obs_started": self.vip_priority_obs_started,
        }


def booked_active_ids(ccs_path: Path) -> set[str]:
    """Student IDs that started in the booked cohort (Active, REENROLL dropped)."""
    ccs = utils.load_ccs_csv(ccs_path)
    enroll_type = (
        ccs[utils.CCS_COLUMNS["enrollment_type"]].astype("string").fillna("").str.strip().str.upper()
    )
    ccs = ccs[enroll_type != utils.ENROLLMENT_TYPE_REENROLL]
    status = ccs[utils.CCS_COLUMNS["enrollment_status"]].astype("string").fillna("").str.strip()
    ids = ccs[utils.CCS_COLUMNS["student_id"]].astype("string").fillna("").str.strip()
    return set(ids[status == utils.ENROLLMENT_STATUS_ACTIVE])


def _window_enroll_lists(
    start_date: date, raw_dir: Path, window_days: int
) -> list[tuple[date, Path]]:
    out: list[tuple[date, Path]] = []
    if not raw_dir.exists():
        return out
    for p in raw_dir.iterdir():
        el = p / ENROLL_LIST_FILENAME
        if not (p.is_dir() and el.exists()):
            continue
        try:
            d = utils.parse_snapshot_date(p.name)
        except ValueError:
            continue
        if 0 <= (start_date - d).days < window_days:
            out.append((d, el))
    return sorted(out)


def observe(
    cohort: str,
    start_date: date,
    started_ids: set[str],
    raw_dir: Path | None = None,
    window_days: int = FAR_REGIME_THRESHOLD,
) -> TierObservation | None:
    """Tier observations for one booked cohort; None when no EnrollList falls in
    the window (calibration then falls back to the at-start columns)."""
    raw_dir = raw_dir or utils.RAW_DIR
    files = _window_enroll_lists(start_date, raw_dir, window_days)
    if not files:
        return None
    wbh_pairs = wbh_started = pool_pairs = pool_started = 0
    for _, path in files:
        el = utils.load_enroll_list(path)
        cohort_col = ingest._el_str(el, "cohort")
        admission = ingest._el_str(el, "admission_type").str.upper()
        group = el[(cohort_col == cohort) & (admission != utils.ENROLLMENT_TYPE_REENROLL)]
        group = group.reset_index(drop=True)
        if group.empty:
            continue
        flags = ingest._parse_action_flags_el(group)
        ids = ingest._el_str(group, "student_id")
        started = ids.isin(started_ids)
        pool = ingest.vip_priority_students(flags)
        wbh_pairs += int(flags["wbh"].sum())
        wbh_started += int((flags["wbh"] & started).sum())
        pool_pairs += int(pool.sum())
        pool_started += int((pool & started).sum())
    return TierObservation(
        snapshots_used=len(files),
        wbh_obs_pairs=wbh_pairs,
        wbh_obs_started=wbh_started,
        vip_priority_obs_pairs=pool_pairs,
        vip_priority_obs_started=pool_started,
    )


def at_start_tiers(
    cohort: str,
    start_date: date,
    started_ids: set[str],
    raw_dir: Path | None = None,
    window_days: int = FAR_REGIME_THRESHOLD,
) -> dict | None:
    """The *_at_start / *_that_started tier columns by student-ID join: flags
    from the last EnrollList on or before start (within the window), started =
    in the booked CCS Active set. None when no EnrollList is available; the
    caller must then leave the tier columns blank, never fall back to the
    booked CCS Action Status (it is cleared on show)."""
    raw_dir = raw_dir or utils.RAW_DIR
    files = _window_enroll_lists(start_date, raw_dir, window_days)
    if not files:
        return None
    snap_date, path = files[-1]
    el = utils.load_enroll_list(path)
    cohort_col = ingest._el_str(el, "cohort")
    admission = ingest._el_str(el, "admission_type").str.upper()
    group = el[(cohort_col == cohort) & (admission != utils.ENROLLMENT_TYPE_REENROLL)]
    group = group.reset_index(drop=True)
    flags = ingest._parse_action_flags_el(group)
    started = ingest._el_str(group, "student_id").isin(started_ids)
    any_priority = flags[["p_fa", "p_va", "p_acc", "p_adm"]].any(axis=1)
    pool = ingest.vip_priority_students(flags)

    out: dict = {"at_start_snapshot": snap_date.isoformat()}
    for name, mask in [
        ("wbh", flags["wbh"]),
        ("vip", flags["vip"]),
        ("priority", any_priority),
        ("vip_priority", pool),
    ]:
        out[f"{name}_at_start"] = int(mask.sum())
        out[f"{name}_that_started"] = int((mask & started).sum())
    return out
