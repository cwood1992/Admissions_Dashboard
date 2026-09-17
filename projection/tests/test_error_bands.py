"""Observed-error bands: table build, application, independent roll-up."""
import math

import pandas as pd
import pytest

from scripts import error_bands as eb
from scripts.projections import Projection, apply_error_band

CONFIG = eb.BandConfig(k=1.28, buckets=[(0, 7), (8, 30), (31, None)], min_cohorts_per_bucket=2)


def _errors(rows):
    return pd.DataFrame(rows, columns=["cohort", "class_number", "days_to_start", "z"])


def test_band_table_uses_one_median_z_per_cohort():
    errors = _errors([
        ["UDT900", 900, 40, 1.0], ["UDT900", 900, 50, 3.0], ["UDT900", 900, 60, 2.0],  # median 2
        ["NDT900", 900, 45, -1.0],
        ["UDT900", 900, 5, 0.5], ["NDT900", 900, 5, -0.5],
    ])
    table = eb.build_band_table(errors, CONFIG).set_index("days_lo")
    far = table.loc[31]
    assert far["n_cohorts"] == 2
    assert far["rms_z"] == pytest.approx(math.sqrt((2.0 ** 2 + 1.0 ** 2) / 2), abs=1e-4)
    assert far["source"] == "own"
    assert table.loc[0, "band_rms_z"] == pytest.approx(0.5)


def test_thin_bucket_borrows_the_wider_neighbour():
    errors = _errors([
        ["UDT900", 900, 5, 0.5], ["NDT900", 900, 5, -0.5],
        ["UDT900", 900, 20, 9.0],                                  # one cohort: too thin
        ["UDT900", 900, 40, 2.0], ["NDT900", 900, 45, -2.0],
    ])
    mid = eb.build_band_table(errors, CONFIG).set_index("days_lo").loc[8]
    assert mid["n_cohorts"] == 1
    assert mid["band_rms_z"] == pytest.approx(2.0)   # from the 31+ bucket, not its own 9.0
    assert mid["source"] == "borrowed:31d"


def test_apply_band_keeps_mid_and_scales_with_sqrt_mid():
    bands = eb.ErrorBands(k=1.28, bands=[eb.Band(0, 7, 0.5, 10), eb.Band(31, None, 2.0, 7)])
    low, high, half, band = bands.apply(16, 45)
    assert half == pytest.approx(1.28 * 2.0 * 4)      # 10.24
    assert (low, high) == (5, 27)
    assert band.label == "31+d"
    assert bands.apply(1, 45)[0] == 0                  # low never negative
    assert bands.apply(16, 20) is None                 # no bucket covers 8-30


def test_apply_error_band_annotates_basis_and_falls_back():
    proj = Projection(14, 16, 18, "far-30+: accum")
    bands = eb.ErrorBands(k=1.28, bands=[eb.Band(31, None, 2.0, 7)])
    out = apply_error_band(proj, 45, bands)
    assert (out.proj_low, out.proj_mid, out.proj_high) == (5, 16, 27)
    assert out.projection_basis.startswith("far-30+: accum | band +/-10.2")
    assert apply_error_band(proj, 10, bands) == proj   # no bucket: regime band kept
    assert apply_error_band(proj, 45, None) == proj


def test_combine_independent_adds_in_quadrature():
    low, mid, high = eb.combine_independent([(7, 10, 14), (12, 16, 19), (10, 10, 10)])
    assert mid == 36
    assert low == pytest.approx(36 - 5)      # sqrt(3^2 + 4^2)
    assert high == pytest.approx(36 + 5)     # sqrt(4^2 + 3^2)
    assert eb.combine_independent_int([(10, 10, 10)]) == (10, 10, 10)


def test_load_error_bands_missing_table_is_none(tmp_path):
    assert eb.load_error_bands(tmp_path / "nope.csv") is None


def test_shipped_config_and_table_are_consistent():
    config = eb.load_config()
    assert config.k == pytest.approx(1.28)
    bands = eb.load_error_bands()
    assert bands is not None
    assert [(b.days_lo, b.days_hi) for b in bands.bands] == config.buckets
    assert all(b.rms_z > 0 for b in bands.bands)
