"""Booked-class CCS -> cohort actuals derivation + calibration end-to-end."""
import pandas as pd
import pytest

from scripts import calibrate as calibrate_mod
from scripts.record_actuals import derive_from_booked_ccs
from scripts.utils import PROJECT_ROOT

BOOKED = PROJECT_ROOT / "tests" / "fixtures" / "booked" / "CCS-U566-booked.csv"


def test_derive_from_booked_ccs_counts():
    row = derive_from_booked_ccs("UDT566", BOOKED)
    assert row["cohort"] == "UDT566"
    assert row["program"] == "UDT"
    assert row["total_ever_enrolled"] == 6
    assert row["actual_starts"] == 4          # 4x "Active Earning"
    assert row["wbh_at_start"] == 3
    assert row["wbh_that_started"] == 2       # ST1, ST2 (ST3 cancelled)
    assert row["vip_at_start"] == 2
    assert row["vip_that_started"] == 1       # ST4 (ST5 cancelled)
    assert row["priority_at_start"] == 1
    assert row["priority_that_started"] == 1  # ST6 P-FA started
    assert row["calibrated_at"] == ""


def test_derived_row_feeds_calibration():
    row = derive_from_booked_ccs("UDT566", BOOKED)
    actuals = pd.DataFrame([row])
    ate = pd.DataFrame(
        [{"program": "UDT", "low": 0.09, "mid": 0.115, "high": 0.14}]
    ).set_index("program")
    tier = pd.DataFrame(
        [
            {"tier": "WBH", "conversion_rate": 0.90, "confidence": "placeholder-data-starved"},
            {"tier": "VIP", "conversion_rate": 0.50, "confidence": "placeholder-data-starved"},
            {"tier": "Priority", "conversion_rate": 0.30, "confidence": "placeholder-data-starved"},
        ]
    ).set_index("tier")

    new_ate, new_tier, result = calibrate_mod.calibrate(actuals, ate, tier)

    # ATE observed = 4/6 = 0.667; blended with prior mid 0.115 at lr=0.2.
    assert new_ate.loc["UDT", "mid"] == pytest.approx(0.115 * 0.8 + (4 / 6) * 0.2, abs=1e-4)
    # WBH observed = 2/3; tier rate flips to calibrated.
    assert new_tier.loc["WBH", "confidence"] == "calibrated"
    assert result.cohorts_processed == ["UDT566"]


def test_blank_total_skips_ate_but_not_tier():
    # Simulate an EnrollList-sourced row with no total_ever_enrolled.
    actuals = pd.DataFrame(
        [
            {
                "cohort": "UDT566",
                "program": "UDT",
                "actual_starts": 10,
                "total_ever_enrolled": "",
                "wbh_at_start": 8,
                "wbh_that_started": 6,
                "vip_at_start": 4,
                "vip_that_started": 2,
                "priority_at_start": 2,
                "priority_that_started": 1,
                "proj_at_60d": "",
                "proj_at_30d": "",
                "proj_at_14d": "",
                "proj_at_7d": "",
                "calibrated_at": "",
            }
        ]
    )
    ate = pd.DataFrame(
        [{"program": "UDT", "low": 0.09, "mid": 0.115, "high": 0.14}]
    ).set_index("program")
    tier = pd.DataFrame(
        [
            {"tier": "WBH", "conversion_rate": 0.90, "confidence": "placeholder"},
            {"tier": "VIP", "conversion_rate": 0.50, "confidence": "placeholder"},
            {"tier": "Priority", "conversion_rate": 0.30, "confidence": "placeholder"},
        ]
    ).set_index("tier")

    new_ate, new_tier, _ = calibrate_mod.calibrate(actuals, ate, tier)
    # ATE untouched (blank denominator), tier still updated.
    assert new_ate.loc["UDT", "mid"] == 0.115
    assert new_tier.loc["WBH", "conversion_rate"] != 0.90
