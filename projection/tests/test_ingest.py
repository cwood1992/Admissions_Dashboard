from datetime import date

import pytest

from scripts.ingest import ingest_cohort_csv, snapshot_to_flat_dict
from scripts.utils import PROJECT_ROOT

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "2026-05-12" / "UDT566.csv"


@pytest.fixture(scope="module")
def snap():
    # Use a synthetic start_dates so the test doesn't depend on the real
    # production baseline file evolving over time.
    return ingest_cohort_csv(FIXTURE, "2026-05-12", start_dates={"UDT566": date(2026, 7, 15)})


def test_identity_fields(snap):
    assert snap.snapshot_date == date(2026, 5, 12)
    assert snap.cohort == "UDT566"
    assert snap.program == "UDT"
    assert snap.start_date == date(2026, 7, 15)
    assert snap.days_to_start == 64


def test_aggregate_counts(snap):
    expected = dict(
        total_ever_enrolled=15,
        currently_enrolled=12,
        new_enrolled=10,
        transfer_enrolled=2,
        reenroll_enrolled=0,
        cancelled_total=3,
        cancelled_gone=2,
        cancelled_moved_later=1,
        wbh_count=2,
        vip_count=2,
        p_fa_count=2,
        p_va_count=1,
        p_acc_count=2,
        p_adm_count=1,
        untagged_count=3,
    )
    flat = snapshot_to_flat_dict(snap)
    for k, v in expected.items():
        assert flat[k] == v, f"{k}: got {flat[k]}, expected {v}"


def test_transfer_chain_uses_next_cohort_field(snap):
    # S009 cancelled from UDT566 with NEXT Cohort = UDT568 → cancelled-moved-later.
    # S010 and S013 cancelled with NEXT Cohort blank → cancelled-gone.
    assert snap.cancelled_moved_later == 1
    assert snap.cancelled_gone == 2


def test_action_status_variants_parsed(snap):
    # 'WBH 100%' counts as WBH; 'P FA' (space) counts as P-FA;
    # 'VIP, P-Acc' counts as both.
    assert snap.wbh_count == 2          # 'WBH' + 'WBH 100%'
    assert snap.p_fa_count == 2         # 'P-FA' + 'P FA'
    assert snap.p_acc_count == 2        # 'P-Acc' + 'VIP, P-Acc'


def test_per_rep_breakdown(snap):
    by_name = {r.rep_name: r for r in snap.reps}
    assert set(by_name) == {"Sarah", "Mike"}

    sarah = by_name["Sarah"]
    assert sarah.rep_total_assigned == 8
    assert sarah.rep_currently_enrolled == 6
    assert sarah.rep_new == 5
    assert sarah.rep_transfer == 1
    assert sarah.rep_cancelled == 2
    assert sarah.rep_cancel_rate == 0.25
    assert sarah.rep_wbh == 1
    assert sarah.rep_vip == 1
    assert sarah.rep_priority == 2

    mike = by_name["Mike"]
    assert mike.rep_total_assigned == 7
    assert mike.rep_currently_enrolled == 6
    assert mike.rep_new == 5
    assert mike.rep_transfer == 1
    assert mike.rep_cancelled == 1
    assert mike.rep_cancel_rate == round(1 / 7, 4)
    assert mike.rep_wbh == 1
    assert mike.rep_vip == 1
    assert mike.rep_priority == 4    # P-VA, P-Acc, P-Adm, (VIP+P-Acc)


def test_per_rep_totals_sum_to_cohort(snap):
    assert sum(r.rep_total_assigned for r in snap.reps) == snap.total_ever_enrolled
    assert sum(r.rep_currently_enrolled for r in snap.reps) == snap.currently_enrolled
    assert sum(r.rep_cancelled for r in snap.reps) == snap.cancelled_total


def test_no_start_date_yields_none_days_to_start():
    snap_no_date = ingest_cohort_csv(FIXTURE, "2026-05-12", start_dates={})
    assert snap_no_date.start_date is None
    assert snap_no_date.days_to_start is None
