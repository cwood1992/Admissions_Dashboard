from pathlib import Path

import pandas as pd
import pytest

from scripts.ingest import ingest_snapshot_dir
from scripts.projections import (
    Projection,
    load_position_averages,
    project_dataframe,
    project_trivial,
)
from scripts.utils import BASELINES_DIR


def test_trivial_bounds_at_15_percent():
    p = project_trivial(currently_enrolled=10, position_avg=20)
    assert p == Projection(proj_low=17, proj_mid=20, proj_high=22, projection_basis=p.projection_basis)
    assert "trivial-v0" in p.projection_basis


def test_low_floored_at_currently_enrolled():
    # currently_enrolled (25) exceeds position_avg (20) — low must not regress below current.
    p = project_trivial(currently_enrolled=25, position_avg=20)
    assert p.proj_low >= 25
    assert p.proj_low <= p.proj_mid <= p.proj_high


def test_missing_position_average_uses_fallback():
    p = project_trivial(currently_enrolled=8, position_avg=None)
    assert "needs baseline seeding" in p.projection_basis
    assert p.proj_low <= p.proj_mid <= p.proj_high


@pytest.mark.parametrize(
    "current,pos",
    [(0, 5), (1, 1), (10, 10), (15, 20), (40, 18), (3, 100)],
)
def test_invariant_low_le_mid_le_high(current, pos):
    p = project_trivial(currently_enrolled=current, position_avg=pos)
    assert p.proj_low <= p.proj_mid <= p.proj_high, p


def test_baselines_file_loads_with_all_25_cohorts():
    pos = load_position_averages()
    expected = {
        # 10 UDT
        *(f"UDT{n}" for n in range(566, 576)),
        # 10 NDT-Day
        *(f"NDT{n}" for n in range(566, 576)),
        # 5 NDT-Night (NC suffix)
        *(f"NDT{n}NC" for n in (566, 568, 570, 572, 574)),
    }
    # The lookup may also contain historical cohorts (562-565) carried in
    # program_start_dates_2026.csv for reference; extra keys are harmless
    # since callers use pos.get(cohort). Just verify the 25 active cohorts
    # are all present and every value is positive.
    assert expected <= set(pos.keys())
    assert all(v > 0 for v in pos.values())


def test_ate_rates_file_loads_with_three_programs():
    df = pd.read_csv(BASELINES_DIR / "ate_conversion_rates.csv").set_index("program")
    assert set(df.index) == {"UDT", "NDT-Day", "NDT-Night"}
    for program in df.index:
        assert df.loc[program, "low"] < df.loc[program, "mid"] < df.loc[program, "high"]


def test_project_dataframe_full_snapshot(full_snapshot_dir: Path):
    cohort_df, _ = ingest_snapshot_dir("2026-05-12", full_snapshot_dir)
    projected = project_dataframe(cohort_df)
    assert len(projected) == 25
    for _, row in projected.iterrows():
        assert row["proj_low"] <= row["proj_mid"] <= row["proj_high"], row.to_dict()
        assert isinstance(row["projection_basis"], str) and row["projection_basis"]
