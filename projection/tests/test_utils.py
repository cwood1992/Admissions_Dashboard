from datetime import date

from scripts import utils


def test_project_root_contains_pyproject():
    assert (utils.PROJECT_ROOT / "pyproject.toml").exists()


def test_known_dirs_resolve_under_root():
    for d in (
        utils.RAW_DIR,
        utils.SNAPSHOTS_DIR,
        utils.BASELINES_DIR,
        utils.COMPLETED_DIR,
        utils.DASHBOARD_DATA_DIR,
    ):
        assert d.is_relative_to(utils.PROJECT_ROOT)


def test_parse_snapshot_date_accepts_string_and_date():
    assert utils.parse_snapshot_date("2026-05-12") == date(2026, 5, 12)
    assert utils.parse_snapshot_date(date(2026, 5, 12)) == date(2026, 5, 12)


def test_snapshot_dir_for_uses_iso_format():
    d = utils.snapshot_dir_for("2026-05-12")
    assert d.name == "2026-05-12"
    assert d.parent == utils.RAW_DIR


def test_expected_cohort_counts():
    assert sum(utils.EXPECTED_COHORT_COUNTS.values()) == 25
