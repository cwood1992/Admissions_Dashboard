"""Hand-computed tests for the consolidated EnrollList ingest path."""
from datetime import date

import pandas as pd
import pytest

from scripts.ingest import ingest_enroll_list, ingest_snapshot_dir
from tests.conftest import ENROLL_LIST_FIXTURE, TEST_START_DATES

SNAP = "2026-05-15"


@pytest.fixture(scope="module")
def cohort_df():
    df, _ = ingest_enroll_list(ENROLL_LIST_FIXTURE, SNAP, start_dates=TEST_START_DATES)
    return df


@pytest.fixture(scope="module")
def rep_df():
    _, reps = ingest_enroll_list(ENROLL_LIST_FIXTURE, SNAP, start_dates=TEST_START_DATES)
    return reps


def _row(df, cohort):
    return df[df["cohort"] == cohort].iloc[0]


def test_emits_full_expected_cohort_universe(cohort_df):
    # 25 expected cohorts from TEST_START_DATES; 3 have data, 22 zero-row.
    assert len(cohort_df) == len(TEST_START_DATES)
    nonzero = cohort_df[cohort_df["currently_enrolled"] > 0]["cohort"].tolist()
    assert sorted(nonzero) == ["NDT566", "UDT566", "UDT567"]


def test_udt566_aggregates(cohort_df):
    r = _row(cohort_df, "UDT566")
    assert r["program"] == "UDT"
    assert r["days_to_start"] == (date(2026, 7, 15) - date(2026, 5, 15)).days  # 61
    assert r["currently_enrolled"] == 7
    assert r["new_enrolled"] == 5
    assert r["transfer_enrolled"] == 2
    assert r["reenroll_enrolled"] == 0
    assert r["wbh_count"] == 2          # 'WBH' + 'WBH 100%'
    assert r["vip_count"] == 2          # S002, S007
    assert r["p_fa_count"] == 1
    assert r["p_acc_count"] == 1        # from 'VIP, P-Acc'
    assert r["p_va_count"] == 0
    assert r["p_adm_count"] == 0
    assert r["untagged_count"] == 2     # S004, S005
    assert r["cold_count"] == 1         # S005 enrolled 2026-04-01 (>14d)
    assert r["new_untagged_count"] == 1 # S004 enrolled 2026-05-12 (<=14d)
    assert r["transferred_in_count"] == 2  # S003 (prev UDT565), S007 (prev UDT564)
    assert r["weekly_velocity"] == 3    # S003/S004/S006 enrolled within 7d of 5/15
    # Old-format-only fields are absent/None for EnrollList.
    assert pd.isna(r.get("total_ever_enrolled"))


def test_zero_row_cohort_is_emitted(cohort_df):
    r = _row(cohort_df, "UDT575")
    assert r["currently_enrolled"] == 0
    assert r["wbh_count"] == 0
    assert r["weekly_velocity"] == 0
    assert r["cold_count"] == 0


def test_per_rep_breakdown(rep_df):
    udt566 = rep_df[rep_df["cohort"] == "UDT566"]
    by = {r["rep_name"]: r for _, r in udt566.iterrows()}
    assert set(by) == {"Sarah", "Mike"}

    sarah = by["Sarah"]
    assert sarah["rep_total_assigned"] == 4
    assert sarah["rep_currently_enrolled"] == 4
    assert sarah["rep_new"] == 2
    assert sarah["rep_transfer"] == 2
    assert sarah["rep_wbh"] == 1
    assert sarah["rep_vip"] == 2
    assert sarah["rep_priority"] == 2   # S003 P-FA, S007 P-Acc
    assert sarah["rep_cancelled"] == 0  # not in EnrollList

    mike = by["Mike"]
    assert mike["rep_total_assigned"] == 3
    assert mike["rep_new"] == 3
    assert mike["rep_wbh"] == 1


def test_ndt566_and_udt567(cohort_df):
    ndt = _row(cohort_df, "NDT566")
    assert ndt["program"] == "NDT-Day"
    assert ndt["currently_enrolled"] == 2
    assert ndt["wbh_count"] == 1
    assert ndt["new_untagged_count"] == 1   # S008 enrolled 2026-05-13
    assert ndt["weekly_velocity"] == 1

    u567 = _row(cohort_df, "UDT567")
    assert u567["currently_enrolled"] == 2
    assert u567["vip_count"] == 1
    assert u567["untagged_count"] == 1
    assert u567["cold_count"] == 1          # S011 enrolled 2026-04-20 (>14d)
    assert u567["weekly_velocity"] == 0


def test_out_of_window_cohort_ignored_not_raised(tmp_path, capsys):
    # The consolidated "All Enrolled Students" export spans started/historical
    # cohorts too. Out-of-window cohorts are silently dropped (reported, not
    # an error) so the pipeline keeps running on the future window.
    from scripts.utils import load_enroll_list

    bad = tmp_path / "EnrollList.csv"
    base = load_enroll_list(ENROLL_LIST_FIXTURE)  # handles preamble + tab header
    base.loc[0, "Current Cohort"] = "UDT559"  # already-started, not in window
    bad.write_text(base.to_csv(index=False), encoding="utf-8")

    cohort_df, _ = ingest_enroll_list(
        bad, SNAP, start_dates=TEST_START_DATES, strict=True
    )
    # UDT559 is not emitted; the remaining in-window cohorts still are.
    assert "UDT559" not in set(cohort_df["cohort"])
    assert len(cohort_df) == len(TEST_START_DATES)
    assert "out-of-window" in capsys.readouterr().out


def test_ingest_snapshot_dir_autodetects_enroll_list(full_enroll_list_dir):
    cohort_df, rep_df = ingest_snapshot_dir(
        SNAP, full_enroll_list_dir, start_dates=TEST_START_DATES
    )
    assert _row(cohort_df, "UDT566")["currently_enrolled"] == 7
