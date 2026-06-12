"""Calibration loop tests with hand-computed weighted-average math."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.calibrate import (
    BIN_CENTERS,
    BIN_RADIUS,
    DEFAULT_LEARNING_RATE,
    MIN_COHORTS_FOR_CURVE_UPDATE,
    _check_escalation,
    _interpolate_prior,
    _nearest_bin,
    calibrate,
    extract_cohort_observations,
    update_accumulation_curves,
    update_ate_rates,
    update_tier_rates,
    write_calibration_log,
)


def _ate_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"program": "UDT", "low": 0.09, "mid": 0.115, "high": 0.14},
            {"program": "NDT-Day", "low": 0.08, "mid": 0.12, "high": 0.16},
            {"program": "NDT-Night", "low": 0.18, "mid": 0.21, "high": 0.24},
        ]
    ).set_index("program")


def _tier_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"tier": "WBH", "conversion_rate": 0.90, "confidence": "placeholder-data-starved"},
            {"tier": "VIP", "conversion_rate": 0.50, "confidence": "placeholder-data-starved"},
            {"tier": "Priority", "conversion_rate": 0.30, "confidence": "placeholder-data-starved"},
        ]
    ).set_index("tier")


def _actuals_row(**overrides) -> dict:
    base = {
        "cohort": "UDT565",
        "program": "UDT",
        "actual_starts": 15,
        "total_ever_enrolled": 150,
        "wbh_at_start": 12,
        "wbh_that_started": 10,
        "vip_at_start": 5,
        "vip_that_started": 3,
        "priority_at_start": 8,
        "priority_that_started": 3,
        "proj_at_60d": 18,
        "proj_at_30d": 17,
        "proj_at_14d": 16,
        "proj_at_7d": 15,
        "calibrated_at": "",
    }
    base.update(overrides)
    return base


def test_ate_rate_updates_via_blend():
    # Observation: 15/150 = 0.10 starts/total. Prior mid 0.115. lr=0.2.
    # new_mid = 0.115*0.8 + 0.10*0.2 = 0.092 + 0.02 = 0.112
    actuals = pd.DataFrame([_actuals_row()])
    new_ate, deltas = update_ate_rates(_ate_baseline(), actuals)
    assert new_ate.loc["UDT", "mid"] == pytest.approx(0.112, abs=1e-4)
    # Low and high shift by the same delta as mid.
    assert new_ate.loc["UDT", "low"] == pytest.approx(0.087, abs=1e-4)
    assert new_ate.loc["UDT", "high"] == pytest.approx(0.137, abs=1e-4)
    assert "UDT ate rate" in deltas[0]


def test_ate_rate_unaffected_for_other_programs():
    actuals = pd.DataFrame([_actuals_row()])
    new_ate, _ = update_ate_rates(_ate_baseline(), actuals)
    assert new_ate.loc["NDT-Day", "mid"] == 0.12
    assert new_ate.loc["NDT-Night", "mid"] == 0.21


def test_tier_rate_updates_and_flips_confidence():
    # WBH: 10/12 = 0.8333. Prior 0.90. lr=0.2.
    # new = 0.90*0.8 + 0.8333*0.2 = 0.72 + 0.1667 = 0.8867
    actuals = pd.DataFrame([_actuals_row()])
    new_tier, deltas = update_tier_rates(_tier_baseline(), actuals)
    assert new_tier.loc["WBH", "conversion_rate"] == pytest.approx(0.8867, abs=1e-3)
    assert new_tier.loc["WBH", "confidence"] == "calibrated"
    # VIP: 3/5 = 0.60. Prior 0.50. new = 0.50*0.8 + 0.60*0.2 = 0.52
    assert new_tier.loc["VIP", "conversion_rate"] == pytest.approx(0.52, abs=1e-3)
    # Priority: 3/8 = 0.375. Prior 0.30. new = 0.30*0.8 + 0.375*0.2 = 0.315
    assert new_tier.loc["Priority", "conversion_rate"] == pytest.approx(0.315, abs=1e-3)


def test_escalation_triggers_on_three_consistent_overshoots():
    # All 3 cohorts: proj_at_30d=20, actual=10 → +100% error each.
    actuals = pd.DataFrame(
        [
            _actuals_row(cohort="C1", proj_at_30d=20, actual_starts=10),
            _actuals_row(cohort="C2", proj_at_30d=20, actual_starts=10),
            _actuals_row(cohort="C3", proj_at_30d=20, actual_starts=10),
        ]
    )
    escalated, reason = _check_escalation(actuals)
    assert escalated is True
    assert "overshot" in reason


def test_escalation_does_not_trigger_on_mixed_errors():
    actuals = pd.DataFrame(
        [
            _actuals_row(cohort="C1", proj_at_30d=20, actual_starts=10),
            _actuals_row(cohort="C2", proj_at_30d=10, actual_starts=20),  # undershot
            _actuals_row(cohort="C3", proj_at_30d=20, actual_starts=10),
        ]
    )
    escalated, _ = _check_escalation(actuals)
    assert escalated is False


def test_escalation_does_not_trigger_under_three_cohorts():
    actuals = pd.DataFrame(
        [
            _actuals_row(cohort="C1", proj_at_30d=20, actual_starts=10),
            _actuals_row(cohort="C2", proj_at_30d=20, actual_starts=10),
        ]
    )
    escalated, _ = _check_escalation(actuals)
    assert escalated is False


def test_calibrate_returns_processed_cohorts_only_for_pending():
    actuals = pd.DataFrame(
        [
            _actuals_row(cohort="UDT564", calibrated_at="2026-04-01"),  # already calibrated
            _actuals_row(cohort="UDT565"),  # pending
        ]
    )
    _, _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
    assert result.cohorts_processed == ["UDT565"]


def test_write_calibration_log_appends(tmp_path: Path):
    log_path = tmp_path / "calibration_log.md"
    actuals = pd.DataFrame([_actuals_row()])
    _, _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
    write_calibration_log(log_path, result, run_date=date(2026, 8, 1))
    text = log_path.read_text(encoding="utf-8")
    assert "2026-08-01 calibration run" in text
    assert "UDT565" in text
    assert "Model accuracy" in text
    assert "Baseline deltas" in text

    # A second run appends, doesn't overwrite.
    write_calibration_log(log_path, result, run_date=date(2026, 9, 1))
    text = log_path.read_text(encoding="utf-8")
    assert text.count("calibration run") == 2


def test_escalation_writes_flag_to_log(tmp_path: Path):
    log_path = tmp_path / "calibration_log.md"
    actuals = pd.DataFrame(
        [_actuals_row(cohort=f"C{i}", proj_at_30d=20, actual_starts=10) for i in range(3)]
    )
    _, _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
    assert result.escalation_flag is True
    write_calibration_log(log_path, result, run_date=date(2026, 8, 1))
    assert "ESCALATION" in log_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Accumulation curve calibration tests
# ---------------------------------------------------------------------------

def _curves_baseline() -> pd.DataFrame:
    """Standard 5-point-per-program seed curves."""
    rows = []
    for program in ("UDT", "NDT-Day", "NDT-Night"):
        for dts, fill in [(0, 1.0), (14, 0.90), (30, 0.75), (60, 0.40), (90, 0.10)]:
            rows.append({
                "program": program,
                "days_to_start": dts,
                "expected_fill_pct": fill,
                "confidence": "approximate",
                "source": "seeded-from-existing-analysis",
            })
    return pd.DataFrame(rows)


def _write_snapshot(tmp_path: Path, snap_date: str, rows: list[dict]) -> None:
    """Write a minimal snapshot CSV into a snapshots dir."""
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(snap_dir / f"{snap_date}_snapshot.csv", index=False)


class TestNearestBin:
    def test_exact_match(self):
        assert _nearest_bin(14) == 14
        assert _nearest_bin(28) == 28
        assert _nearest_bin(91) == 91

    def test_within_radius(self):
        assert _nearest_bin(15) == 14  # distance 1
        assert _nearest_bin(11) == 14  # distance 3
        assert _nearest_bin(30) == 28  # distance 2

    def test_in_gap_returns_none(self):
        # Between 7 and 14, the midpoint is 10.5. At distance > 3 from both:
        assert _nearest_bin(10) == 7  # distance 3 from 7, within radius
        # 4 is distance 3 from 7 — still in radius
        assert _nearest_bin(4) == 7
        # 18 is distance 3 from 21 — within radius, returns 21
        assert _nearest_bin(18) == 21
        # But values in the true gap (distance > 3 from any center) return None.
        # Between 91 and infinity: 95 is distance 4 from 91, in gap.
        assert _nearest_bin(95) is None

    def test_skips_zero(self):
        # Day 0 should never be returned.
        assert _nearest_bin(0) is None
        assert _nearest_bin(1) is None
        assert _nearest_bin(2) is None
        # Day 3 is within radius of 7 (distance 4) — but also let's check:
        # distance from 7 is 4, > BIN_RADIUS=3. So None.
        assert _nearest_bin(3) is None


class TestExtractCohortObservations:
    def test_correct_observations(self, tmp_path: Path):
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 60, "currently_enrolled": 8, "program": "UDT"},
        ])
        _write_snapshot(tmp_path, "2026-05-08", [
            {"cohort": "UDT567", "days_to_start": 53, "currently_enrolled": 12, "program": "UDT"},
        ])
        obs = extract_cohort_observations("UDT567", 20, tmp_path / "snapshots")
        # day 60 → bin 63 (distance 3, within radius)? No: distance from 60 is |63-60|=3, from 56 is |56-60|=4.
        # Closest is 63 at distance 3.  Wait — 60 is not a bin center.
        # BIN_CENTERS: 0,7,14,21,28,35,42,49,56,63,70,77,84,91
        # |60-56|=4, |60-63|=3 → nearest is 63, distance 3, within radius
        # |53-49|=4, |53-56|=3 → nearest is 56, distance 3, within radius
        assert len(obs) == 2
        assert (63, 8 / 20) in obs
        assert (56, 12 / 20) in obs

    def test_empty_when_no_snapshots(self, tmp_path: Path):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        obs = extract_cohort_observations("UDT567", 20, snap_dir)
        assert obs == []

    def test_zero_total_enrolled(self, tmp_path: Path):
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 60, "currently_enrolled": 5, "program": "UDT"},
        ])
        obs = extract_cohort_observations("UDT567", 0, tmp_path / "snapshots")
        assert obs == []

    def test_skips_day_zero_bin(self, tmp_path: Path):
        _write_snapshot(tmp_path, "2026-06-29", [
            {"cohort": "UDT567", "days_to_start": 0, "currently_enrolled": 20, "program": "UDT"},
        ])
        obs = extract_cohort_observations("UDT567", 20, tmp_path / "snapshots")
        assert obs == []


class TestInterpolatePrior:
    def test_existing_point(self):
        df = _curves_baseline()
        assert _interpolate_prior(df, "UDT", 30) == pytest.approx(0.75)

    def test_new_point_interpolated(self):
        df = _curves_baseline()
        # Between day 14 (0.90) and day 30 (0.75): day 21 is 7/16 of the way.
        # expected = 0.90 + (0.75 - 0.90) * (21 - 14) / (30 - 14)
        #          = 0.90 + (-0.15) * (7/16)
        #          = 0.90 - 0.065625 = 0.834375
        assert _interpolate_prior(df, "UDT", 21) == pytest.approx(0.834375)

    def test_beyond_range(self):
        df = _curves_baseline()
        # Beyond 90 days, should clamp to the 90-day value.
        assert _interpolate_prior(df, "UDT", 100) == pytest.approx(0.10)


class TestUpdateAccumulationCurves:
    def _make_completed(self, cohorts: list[dict]) -> pd.DataFrame:
        rows = []
        for c in cohorts:
            rows.append({
                "cohort": c["cohort"],
                "program": c["program"],
                "actual_starts": c.get("actual_starts", 10),
                "total_ever_enrolled": c["total_ever_enrolled"],
                "calibrated_at": "",
            })
        return pd.DataFrame(rows)

    def test_blends_correctly(self, tmp_path: Path):
        """Two UDT cohorts with observations at bin 63 (≈day 60). Verify blend math."""
        # Cohort 1: at day 60 → bin 63, 8/20 = 0.40 fill
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 60, "currently_enrolled": 8, "program": "UDT"},
            {"cohort": "UDT568", "days_to_start": 62, "currently_enrolled": 6, "program": "UDT"},
        ])
        completed = self._make_completed([
            {"cohort": "UDT567", "program": "UDT", "total_ever_enrolled": 20},
            {"cohort": "UDT568", "program": "UDT", "total_ever_enrolled": 20},
        ])
        curves = _curves_baseline()
        new_curves, deltas = update_accumulation_curves(
            curves, completed, snapshots_dir=tmp_path / "snapshots"
        )
        # Bin 63: obs from UDT567 = 8/20=0.40, UDT568 = 6/20=0.30. Mean = 0.35.
        # Prior at bin 63 (interpolated): between day 60 (0.40) and day 90 (0.10):
        #   0.40 + (0.10 - 0.40) * (63 - 60) / (90 - 60) = 0.40 - 0.03 = 0.37
        # Blended: 0.37 * 0.8 + 0.35 * 0.2 = 0.296 + 0.07 = 0.366
        row_63 = new_curves[
            (new_curves["program"] == "UDT") & (new_curves["days_to_start"] == 63)
        ]
        assert len(row_63) == 1
        assert row_63.iloc[0]["expected_fill_pct"] == pytest.approx(0.366, abs=1e-3)
        assert "calibrated" in row_63.iloc[0]["confidence"]
        assert len(deltas) >= 1

    def test_adds_new_bins(self, tmp_path: Path):
        """New bin centers appear as rows in the DataFrame."""
        _write_snapshot(tmp_path, "2026-05-15", [
            {"cohort": "UDT567", "days_to_start": 42, "currently_enrolled": 14, "program": "UDT"},
            {"cohort": "UDT568", "days_to_start": 42, "currently_enrolled": 16, "program": "UDT"},
        ])
        completed = self._make_completed([
            {"cohort": "UDT567", "program": "UDT", "total_ever_enrolled": 20},
            {"cohort": "UDT568", "program": "UDT", "total_ever_enrolled": 20},
        ])
        curves = _curves_baseline()
        # Day 42 is a bin center. Not in original 5 points.
        assert not (curves["days_to_start"] == 42).any()
        new_curves, _ = update_accumulation_curves(
            curves, completed, snapshots_dir=tmp_path / "snapshots"
        )
        row_42 = new_curves[
            (new_curves["program"] == "UDT") & (new_curves["days_to_start"] == 42)
        ]
        assert len(row_42) == 1

    def test_requires_min_cohorts(self, tmp_path: Path):
        """Single cohort → no update."""
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 60, "currently_enrolled": 8, "program": "UDT"},
        ])
        completed = self._make_completed([
            {"cohort": "UDT567", "program": "UDT", "total_ever_enrolled": 20},
        ])
        curves = _curves_baseline()
        new_curves, deltas = update_accumulation_curves(
            curves, completed, snapshots_dir=tmp_path / "snapshots"
        )
        # Should be unchanged — single cohort below threshold.
        assert deltas == []
        pd.testing.assert_frame_equal(
            new_curves.sort_values(["program", "days_to_start"]).reset_index(drop=True),
            curves.sort_values(["program", "days_to_start"]).reset_index(drop=True),
        )

    def test_monotonicity_enforcement(self, tmp_path: Path):
        """If blended fill_pct violates monotonicity, clamp it."""
        # Set up: observations that would push fill_pct at day 28 above day 14.
        # day 14 seed = 0.90. If we observe very high fill at day 28 it could exceed 0.90.
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 28, "currently_enrolled": 19, "program": "UDT"},
            {"cohort": "UDT568", "days_to_start": 28, "currently_enrolled": 19, "program": "UDT"},
        ])
        completed = self._make_completed([
            {"cohort": "UDT567", "program": "UDT", "total_ever_enrolled": 20},
            {"cohort": "UDT568", "program": "UDT", "total_ever_enrolled": 20},
        ])
        curves = _curves_baseline()
        new_curves, deltas = update_accumulation_curves(
            curves, completed, snapshots_dir=tmp_path / "snapshots"
        )
        # Verify the curve is monotonically non-increasing as days_to_start increases.
        udt = new_curves[new_curves["program"] == "UDT"].sort_values("days_to_start")
        fills = udt["expected_fill_pct"].tolist()
        for i in range(len(fills) - 1):
            assert fills[i] >= fills[i + 1], (
                f"Monotonicity violated at index {i}: {fills[i]} < {fills[i+1]}"
            )

    def test_per_program_isolation(self, tmp_path: Path):
        """UDT observations don't affect NDT-Day curve."""
        _write_snapshot(tmp_path, "2026-05-01", [
            {"cohort": "UDT567", "days_to_start": 60, "currently_enrolled": 5, "program": "UDT"},
            {"cohort": "UDT568", "days_to_start": 60, "currently_enrolled": 5, "program": "UDT"},
        ])
        completed = self._make_completed([
            {"cohort": "UDT567", "program": "UDT", "total_ever_enrolled": 20},
            {"cohort": "UDT568", "program": "UDT", "total_ever_enrolled": 20},
        ])
        curves = _curves_baseline()
        new_curves, _ = update_accumulation_curves(
            curves, completed, snapshots_dir=tmp_path / "snapshots"
        )
        # NDT-Day should be completely unchanged.
        ndt_orig = curves[curves["program"] == "NDT-Day"].sort_values("days_to_start").reset_index(drop=True)
        ndt_new = new_curves[new_curves["program"] == "NDT-Day"].sort_values("days_to_start").reset_index(drop=True)
        pd.testing.assert_frame_equal(ndt_orig, ndt_new)


def test_calibrate_backward_compat():
    """When curves_df is not passed, calibrate returns None in the curves slot."""
    actuals = pd.DataFrame([_actuals_row()])
    new_ate, new_tier, new_curves, result = calibrate(
        actuals, _ate_baseline(), _tier_baseline()
    )
    assert new_curves is None
    assert len(result.cohorts_processed) == 1
