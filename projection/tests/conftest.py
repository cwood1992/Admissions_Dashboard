from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from scripts.utils import PROJECT_ROOT

UDT566_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "2026-05-12" / "UDT566.csv"
ENROLL_LIST_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "2026-05-15" / "EnrollList.csv"

# (filename_stem, cohort_code) — filename matches real CCS naming:
#   CCS-U###   for UDT###
#   CCS-N###   for NDT### (NDT-Day)
#   CCS-NNC### for NDT###NC (NDT-Night)
# UDT566 is the real-fixture slot; the rest are stubs.
STUB_LAYOUT: list[tuple[str, str]] = [
    *[(f"CCS-U{n}", f"UDT{n}") for n in range(567, 576)],          # 9 UDT stubs
    *[(f"CCS-N{n}", f"NDT{n}") for n in range(566, 576)],          # 10 NDT-Day stubs
    *[(f"CCS-NNC{n}", f"NDT{n}NC") for n in (566, 568, 570, 572, 574)],  # 5 NDT-Night
]

# Synthetic start dates used by tests that need consistent days_to_start values.
TEST_START_DATES: dict[str, date] = {
    "UDT566": date(2026, 7, 15),
}
TEST_START_DATES.update({cohort: date(2026, 8, 1) for _, cohort in STUB_LAYOUT})


def _stub_csv_text(cohort: str) -> str:
    """Minimal real-CCS-schema CSV with one enrolled WBH student."""
    return (
        '"Selected School: The Ocean Corp"\n'
        '"Admissions Department Class Control Sheet (All Enrolled Students)"\n'
        '"As Of: 05/12/2026, 12:00:00"\n'
        f'"Selected Cohort: \'{cohort}\'"\n'
        '"Total Records: 1"\n'
        '\n'
        '"Enroll Type","Action Status","ID","Student Name","Lead Rep","Lead Origin","Response Mode","PREV Cohort","PREV Status","CCS Cohort","CCS Status","NEXT Cohort","NEXT Status","Current Cohort","Current Status","FULL Student Name","FULL Current Status"\n'
        f'"NEW","WBH","STUB-{cohort}","Stub Student","Stub Rep","INTERNET","Sales Force","","","{cohort}","Enroll","","","{cohort}","Enroll","Stub Student","Enrolled Student"\n'
    )


def _write_stub_csv(path: Path, cohort: str) -> None:
    path.write_text(_stub_csv_text(cohort), encoding="utf-8")


@pytest.fixture
def full_snapshot_dir(tmp_path: Path) -> Path:
    """Build a complete 25-cohort raw snapshot directory in tmp_path."""
    snapshot_dir = tmp_path / "2026-05-12"
    snapshot_dir.mkdir()
    shutil.copy(UDT566_FIXTURE, snapshot_dir / "CCS-U566.csv")
    for stem, cohort in STUB_LAYOUT:
        target = snapshot_dir / f"{stem}.csv"
        if target.exists():
            continue
        _write_stub_csv(target, cohort)
    return snapshot_dir


@pytest.fixture
def full_enroll_list_dir(tmp_path: Path) -> Path:
    """A raw/<date>/ directory containing the consolidated EnrollList.csv."""
    snapshot_dir = tmp_path / "2026-05-15"
    snapshot_dir.mkdir()
    shutil.copy(ENROLL_LIST_FIXTURE, snapshot_dir / "EnrollList.csv")
    return snapshot_dir

