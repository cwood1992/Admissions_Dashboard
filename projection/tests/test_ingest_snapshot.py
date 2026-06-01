from pathlib import Path

import pytest

from scripts.ingest import (
    MissingCohortFilesError,
    ingest_snapshot_dir,
    write_snapshot_files,
)
from tests.conftest import TEST_START_DATES


def test_ingests_full_25_cohort_set(full_snapshot_dir: Path):
    cohort_df, rep_df = ingest_snapshot_dir(
        "2026-05-12", full_snapshot_dir, start_dates=TEST_START_DATES
    )
    assert len(cohort_df) == 25
    by_program = cohort_df["program"].value_counts().to_dict()
    assert by_program == {"UDT": 10, "NDT-Day": 10, "NDT-Night": 5}


def test_real_udt566_passes_through_full_pipeline(full_snapshot_dir: Path):
    cohort_df, rep_df = ingest_snapshot_dir(
        "2026-05-12", full_snapshot_dir, start_dates=TEST_START_DATES
    )
    row = cohort_df[cohort_df["cohort"] == "UDT566"].iloc[0]
    assert int(row["currently_enrolled"]) == 12
    assert int(row["cancelled_moved_later"]) == 1
    udt566_reps = rep_df[rep_df["cohort"] == "UDT566"]
    assert udt566_reps["rep_total_assigned"].sum() == int(row["total_ever_enrolled"])


def test_missing_program_file_flags(full_snapshot_dir: Path):
    (full_snapshot_dir / "CCS-NNC566.csv").unlink()
    with pytest.raises(MissingCohortFilesError, match="NDT-Night.*expected 5.*got 4"):
        ingest_snapshot_dir("2026-05-12", full_snapshot_dir, start_dates=TEST_START_DATES)


def test_non_strict_mode_allows_partial(full_snapshot_dir: Path):
    (full_snapshot_dir / "CCS-NNC566.csv").unlink()
    cohort_df, _ = ingest_snapshot_dir(
        "2026-05-12", full_snapshot_dir, strict=False, start_dates=TEST_START_DATES
    )
    assert len(cohort_df) == 24


def test_write_snapshot_files(full_snapshot_dir: Path, tmp_path: Path):
    cohort_df, rep_df = ingest_snapshot_dir(
        "2026-05-12", full_snapshot_dir, start_dates=TEST_START_DATES
    )
    out = tmp_path / "snapshots"
    cohort_path, rep_path = write_snapshot_files(cohort_df, rep_df, "2026-05-12", out)
    assert cohort_path.name == "2026-05-12_snapshot.csv"
    assert rep_path.name == "2026-05-12_reps.csv"

    import pandas as pd

    reread = pd.read_csv(cohort_path)
    assert len(reread) == 25
    assert set(reread.columns) >= {
        "snapshot_date",
        "cohort",
        "program",
        "currently_enrolled",
        "cancelled_moved_later",
    }


def test_rep_sum_invariant_across_full_snapshot(full_snapshot_dir: Path):
    cohort_df, rep_df = ingest_snapshot_dir(
        "2026-05-12", full_snapshot_dir, start_dates=TEST_START_DATES
    )
    merged = (
        rep_df.groupby("cohort")["rep_total_assigned"]
        .sum()
        .rename("rep_sum")
        .to_frame()
        .merge(cohort_df[["cohort", "total_ever_enrolled"]], on="cohort")
    )
    assert (merged["rep_sum"] == merged["total_ever_enrolled"]).all()
