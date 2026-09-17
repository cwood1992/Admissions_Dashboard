"""Projection accuracy report: grading, summaries, class totals."""
from datetime import date

import pandas as pd
import pytest

from scripts import accuracy_report as ar


def _snapshot(rows):
    return pd.DataFrame(
        rows,
        columns=["cohort", "program", "days_to_start", "currently_enrolled",
                 "proj_low", "proj_mid", "proj_high", "projection_basis"],
    )


ACTUALS = {"UDT900": 10, "NDT900": 20}


def test_grade_snapshot_errors_and_range():
    frame = _snapshot([
        ["UDT900", "UDT", 40, 30, 12, 15, 18, "far-30+: accum"],
        ["NDT900", "NDT-Day", 40, 50, 14, 18, 22, "far-30+: accum"],
        ["UDT901", "UDT", 75, 5, 8, 10, 12, "far-30+: pos_avg"],   # not completed
    ])
    rows = ar.grade_snapshot(frame, date(2030, 1, 1), ACTUALS)
    by = {r["cohort"]: r for r in rows}
    assert set(by) == {"UDT900", "NDT900"}
    assert by["UDT900"]["error"] == 5
    assert by["UDT900"]["pct_error"] == pytest.approx(0.5)
    assert by["UDT900"]["in_range"] is False        # 10 below low of 12
    assert by["NDT900"]["error"] == -2
    assert by["NDT900"]["in_range"] is True
    assert by["NDT900"]["regime"] == "far-30+"
    assert by["NDT900"]["high_water_enrolled"] is None   # old schema, column absent


def test_grade_snapshot_skips_rows_after_start():
    frame = _snapshot([["UDT900", "UDT", -3, 0, 9, 10, 11, "near-<14: x"]])
    assert ar.grade_snapshot(frame, date(2030, 1, 1), ACTUALS) == []


def test_horizon_label_bounds():
    assert ar.horizon_label(0) == "0-7"
    assert ar.horizon_label(7) == "0-7"
    assert ar.horizon_label(8) == "8-14"
    assert ar.horizon_label(30) == "15-30"
    assert ar.horizon_label(31) == "31-60"
    assert ar.horizon_label(200) == "91+"


def _write_inputs(tmp_path):
    snaps = tmp_path / "snapshots"
    done = tmp_path / "completed"
    snaps.mkdir()
    done.mkdir()
    pd.DataFrame(
        [{"cohort": c, "actual_starts": a} for c, a in ACTUALS.items()]
    ).to_csv(done / "cohort_actuals.csv", index=False)
    far = _snapshot([
        ["UDT900", "UDT", 40, 30, 12, 15, 18, "far-30+: accum"],
        ["NDT900", "NDT-Day", 40, 50, 14, 18, 22, "far-30+: accum"],
    ])
    near = _snapshot([
        ["UDT900", "UDT", 5, 20, 9, 10, 11, "near-<14: tiers"],
    ])
    far.to_csv(snaps / "2030-01-01_snapshot.csv", index=False)
    near.to_csv(snaps / "2030-02-05_snapshot.csv", index=False)
    return snaps, done


def test_summarize_pools_errors(tmp_path):
    snaps, done = _write_inputs(tmp_path)
    long, diffs = ar.build_long(snaps, done, use_git=False)
    assert len(long) == 3 and diffs.empty
    assert set(long["version"]) == {ar.VERSION_WORKING}

    far = ar.summarize(long, "regime").set_index("regime").loc["far-30+"]
    assert far["projections"] == 2 and far["cohorts"] == 2
    assert far["mean_error"] == pytest.approx(1.5)          # (+5, -2)
    assert far["mean_abs_error"] == pytest.approx(3.5)
    assert far["bias_pct"] == pytest.approx(3 / 30)
    assert far["wape"] == pytest.approx(7 / 30)
    assert far["in_range_share"] == pytest.approx(0.5)


def test_class_totals_need_every_booked_cohort(tmp_path):
    snaps, done = _write_inputs(tmp_path)
    long, _ = ar.build_long(snaps, done, use_git=False)
    totals = ar.class_totals(long, ACTUALS)
    # The near snapshot only carries UDT900, so only the far one is graded.
    assert list(totals["snapshot_date"]) == ["2030-01-01"]
    row = totals.iloc[0]
    # Mids add (15 + 18); distances to low (3, 4) and high (3, 4) add in quadrature.
    assert (row["proj_low"], row["proj_mid"], row["proj_high"]) == (28, 33, 38)
    assert row["actual_starts"] == 30 and row["error"] == 3
    assert bool(row["in_range"]) is True


def test_write_report_outputs_aggregates_only(tmp_path):
    snaps, done = _write_inputs(tmp_path)
    md_path, csv_path, long = ar.write_report(tmp_path / "reports", snaps, done, use_git=False)
    text = md_path.read_text(encoding="utf-8")
    assert "## By days to start" in text
    assert "### UDT900 (actual starts: 10)" in text
    assert list(pd.read_csv(csv_path).columns) == ar.LONG_COLUMNS
