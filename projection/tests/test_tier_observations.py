"""Horizon-matched tier observations (synthetic students only)."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import calibrate, tier_observations
from scripts.utils import PROJECT_ROOT

START = date(2026, 7, 1)
HEADER = [
    "Admission Type", "ID", "Student Name", "# Enroll", "Current Status",
    "Current Cohort", "Current Enroll Date", "Previous Cohort", "Previous Enroll Date",
    "First Cohort", "First Enroll Date", "Admissions Rep", "Action Status",
    "Lead Origin", "Response Mode", "STATUS CODE DESCRIPTION",
]


def _write_el(raw: Path, snap: str, students: list[tuple[str, str, str]]) -> None:
    """students: (admission_type, id, action_status), all in UDT999."""
    d = raw / snap
    d.mkdir(parents=True)
    rows = [
        {**{h: "" for h in HEADER}, "Admission Type": adm, "ID": sid,
         "Current Status": "Enroll", "Current Cohort": "UDT999", "Action Status": act}
        for adm, sid, act in students
    ]
    pd.DataFrame(rows, columns=HEADER).to_csv(d / "EnrollList.csv", index=False)


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    # 20d out: S1 VIP + P-FA (one student), S2 WBH, S3 untagged, S4 REENROLL VIP.
    _write_el(raw, "2026-06-11", [
        ("NEW", "S1", "VIP, P-FA"), ("NEW", "S2", "WBH"), ("NEW", "S3", ""),
        ("REENROLL", "S4", "VIP"),
    ])
    # 3d out: S1 has become WBH; S3 now P-VA.
    _write_el(raw, "2026-06-28", [
        ("NEW", "S1", "WBH, VIP"), ("NEW", "S2", "WBH"), ("NEW", "S3", "P-VA"),
    ])
    # 45d out: outside the 0-29d window, must be ignored.
    _write_el(raw, "2026-05-17", [("NEW", "S9", "VIP")])
    return raw


def test_observe_counts_student_snapshot_pairs_in_window(raw):
    obs = tier_observations.observe("UDT999", START, {"S1", "S2"}, raw_dir=raw)
    assert obs.snapshots_used == 2
    # WBH pairs: S2 (20d), S1 + S2 (3d) = 3, all started.
    assert (obs.wbh_obs_pairs, obs.wbh_obs_started) == (3, 3)
    # Pool pairs: S1 at 20d (VIP+P-FA counted once), S3 at 3d. S1 at 3d is WBH
    # (excluded), S4 is REENROLL (excluded), S9 is out of window.
    assert (obs.vip_priority_obs_pairs, obs.vip_priority_obs_started) == (2, 1)


def test_observe_none_without_enroll_lists(tmp_path):
    assert tier_observations.observe("UDT999", START, set(), raw_dir=tmp_path) is None


def test_at_start_uses_last_enroll_list_before_start(raw):
    out = tier_observations.at_start_tiers("UDT999", START, {"S1", "S2"}, raw_dir=raw)
    assert out["at_start_snapshot"] == "2026-06-28"
    assert (out["wbh_at_start"], out["wbh_that_started"]) == (2, 2)
    assert (out["vip_at_start"], out["vip_that_started"]) == (1, 1)
    assert (out["priority_at_start"], out["priority_that_started"]) == (1, 0)
    # S1 is WBH so not pooled; S3 (P-VA) is.
    assert (out["vip_priority_at_start"], out["vip_priority_that_started"]) == (1, 0)


def test_booked_active_ids_from_fixture():
    ids = tier_observations.booked_active_ids(
        PROJECT_ROOT / "tests" / "fixtures" / "booked" / "CCS-U566-booked.csv"
    )
    assert "ST4" in ids and "ST5" not in ids


def _tier_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"tier": "WBH", "conversion_rate": 0.90, "confidence": "calibrated"},
            {"tier": "VIP+Priority", "conversion_rate": 0.40, "confidence": "calibrated"},
        ]
    ).set_index("tier")


def test_calibrate_prefers_window_observation():
    row = {
        "cohort": "UDT999",
        "wbh_at_start": 10, "wbh_that_started": 10,
        "wbh_obs_pairs": 40, "wbh_obs_started": 30,
        "vip_priority_at_start": 10, "vip_priority_that_started": 0,
        "vip_priority_obs_pairs": 50, "vip_priority_obs_started": 10,
    }
    new, deltas = calibrate.update_tier_rates(_tier_df(), pd.DataFrame([row]))
    # WBH stays at-start until the missing-starters term exists (see calibrate):
    # at-start 1.0 -> 0.90*0.8 + 1.0*0.2 = 0.92, not the window's 0.75 -> 0.87.
    assert new.loc["WBH", "conversion_rate"] == pytest.approx(0.92, abs=1e-4)
    # Pool obs 0.20: 0.40*0.8 + 0.20*0.2 = 0.36 (at-start 0.0 would give 0.32)
    assert new.loc["VIP+Priority", "conversion_rate"] == pytest.approx(0.36, abs=1e-4)
    assert "at start" in deltas[0] and "0-29d window" in deltas[1]


def test_calibrate_falls_back_to_at_start():
    row = {
        "cohort": "UDT999",
        "wbh_at_start": 10, "wbh_that_started": 5,
        "wbh_obs_pairs": None, "wbh_obs_started": None,
        "vip_priority_at_start": None, "vip_priority_that_started": None,
    }
    new, deltas = calibrate.update_tier_rates(_tier_df(), pd.DataFrame([row]))
    # 0.90*0.8 + 0.5*0.2 = 0.82
    assert new.loc["WBH", "conversion_rate"] == pytest.approx(0.82, abs=1e-4)
    assert "at start" in deltas[0]
    # No pooled data at all: rate untouched.
    assert new.loc["VIP+Priority", "conversion_rate"] == 0.40
