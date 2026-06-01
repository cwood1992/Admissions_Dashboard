"""Calibration loop tests with hand-computed weighted-average math."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.calibrate import (
    DEFAULT_LEARNING_RATE,
    _check_escalation,
    calibrate,
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
    _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
    assert result.cohorts_processed == ["UDT565"]


def test_write_calibration_log_appends(tmp_path: Path):
    log_path = tmp_path / "calibration_log.md"
    actuals = pd.DataFrame([_actuals_row()])
    _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
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
    _, _, result = calibrate(actuals, _ate_baseline(), _tier_baseline())
    assert result.escalation_flag is True
    write_calibration_log(log_path, result, run_date=date(2026, 8, 1))
    assert "ESCALATION" in log_path.read_text(encoding="utf-8")
