"""Per-cohort enrollment high-water-mark tests."""
import pandas as pd

from scripts.high_water import (
    annotate_cohort_df,
    load_high_water,
    mark_superseded,
    update_high_water,
)


def _cohort_df(pairs: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"cohort": c, "currently_enrolled": n} for c, n in pairs]
    )


def test_initializes_on_first_run(tmp_path):
    path = tmp_path / "hw.csv"
    out = update_high_water(_cohort_df([("UDT566", 10), ("NDT566", 4)]), "2026-05-15", path)
    by = {r["cohort"]: r for _, r in out.iterrows()}
    assert by["UDT566"]["high_water_enrolled"] == 10
    assert by["UDT566"]["as_of_snapshot"] == "2026-05-15"
    assert bool(by["UDT566"]["superseded_by_booked_ccs"]) is False


def test_monotonic_non_decreasing(tmp_path):
    path = tmp_path / "hw.csv"
    update_high_water(_cohort_df([("UDT566", 10)]), "2026-05-15", path)
    # Week 2: count grew → high water bumps, as_of updates.
    out = update_high_water(_cohort_df([("UDT566", 14)]), "2026-05-22", path)
    row = out[out["cohort"] == "UDT566"].iloc[0]
    assert row["high_water_enrolled"] == 14
    assert row["as_of_snapshot"] == "2026-05-22"
    # Week 3: count shrank (churn) → high water holds, as_of unchanged.
    out = update_high_water(_cohort_df([("UDT566", 11)]), "2026-05-29", path)
    row = out[out["cohort"] == "UDT566"].iloc[0]
    assert row["high_water_enrolled"] == 14
    assert row["as_of_snapshot"] == "2026-05-22"


def test_new_cohort_added_midstream(tmp_path):
    path = tmp_path / "hw.csv"
    update_high_water(_cohort_df([("UDT566", 10)]), "2026-05-15", path)
    out = update_high_water(
        _cohort_df([("UDT566", 12), ("UDT567", 5)]), "2026-05-22", path
    )
    assert set(out["cohort"]) == {"UDT566", "UDT567"}
    assert out[out["cohort"] == "UDT567"].iloc[0]["high_water_enrolled"] == 5


def test_booked_ccs_supersedes_and_freezes(tmp_path):
    path = tmp_path / "hw.csv"
    update_high_water(_cohort_df([("UDT566", 46)]), "2026-05-15", path)
    mark_superseded("UDT566", exact_total_ever_enrolled=94, path=path)
    df = load_high_water(path)
    row = df[df["cohort"] == "UDT566"].iloc[0]
    assert bool(row["superseded_by_booked_ccs"]) is True
    assert int(row["exact_total_ever_enrolled"]) == 94
    # A later weekly run must NOT touch a superseded cohort.
    out = update_high_water(_cohort_df([("UDT566", 200)]), "2026-05-29", path)
    row = out[out["cohort"] == "UDT566"].iloc[0]
    assert row["high_water_enrolled"] == 46  # unchanged; ground truth wins
    assert bool(row["superseded_by_booked_ccs"]) is True


def test_annotate_cohort_df_left_joins(tmp_path):
    path = tmp_path / "hw.csv"
    hw = update_high_water(_cohort_df([("UDT566", 10)]), "2026-05-15", path)
    cohort_df = pd.DataFrame(
        [{"cohort": "UDT566", "currently_enrolled": 10}, {"cohort": "UDT567", "currently_enrolled": 0}]
    )
    merged = annotate_cohort_df(cohort_df, hw)
    assert "high_water_enrolled" in merged.columns
    assert merged.loc[merged["cohort"] == "UDT566", "high_water_enrolled"].iloc[0] == 10
