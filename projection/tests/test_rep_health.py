"""Rep health scorecard tests (EnrollList schema, prior-based cancel/durability)."""
from datetime import date

import pandas as pd
import pytest

from scripts.rep_health import (
    CANCEL_RATE_UNAVAILABLE_SENTINEL,
    DURABILITY_UNAVAILABLE_SENTINEL,
    compute_rep_scorecards,
)
from scripts.utils import ENROLL_LIST_COLUMNS

SNAPSHOT = date(2026, 5, 12)
C = ENROLL_LIST_COLUMNS


def _row(rep: str, sid: str, action: str = "", cohort: str = "UDT566") -> dict:
    return {
        C["admission_type"]: "NEW",
        C["student_id"]: sid,
        C["student_name"]: "synthetic",
        C["enroll_count"]: "1",
        C["current_status"]: "Enroll",
        C["cohort"]: cohort,
        C["current_enroll_date"]: "2026-04-01",
        C["prev_cohort"]: "",
        C["prev_enroll_date"]: "",
        C["first_cohort"]: cohort,
        C["first_enroll_date"]: "2026-04-01",
        C["rep_name"]: rep,
        C["action_status"]: action,
        C["lead_origin"]: "INTERNET",
        C["response_mode"]: "Sales Force",
        C["status_code_description"]: "Enrolled",
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_basic_metrics_no_prior_snapshot():
    rows = _frame(
        [_row("Sarah", f"W{i}", "WBH") for i in range(4)]
        + [_row("Sarah", f"U{i}", "") for i in range(4)]
    )
    cards = compute_rep_scorecards(rows, SNAPSHOT, new_rep_threshold=2)
    sarah = next(c for c in cards if c.rep_name == "Sarah")
    assert sarah.total_assigned == 8
    assert sarah.currently_enrolled == 8  # every EnrollList row is enrolled
    assert sarah.wbh_rate == 0.5
    # No prior snapshot → cancel_rate & durability unavailable.
    assert sarah.cancel_rate == CANCEL_RATE_UNAVAILABLE_SENTINEL
    assert sarah.durability == DURABILITY_UNAVAILABLE_SENTINEL
    # Quality is wbh_rate alone when the other two terms are unavailable.
    assert sarah.quality_score == 0.5
    assert "needs prior snapshot history" in sarah.note


def test_cancel_rate_and_durability_with_prior():
    prior = _frame(
        [_row("Sarah", "S1"), _row("Sarah", "S2"), _row("Sarah", "S3"), _row("Sarah", "S4")]
    )
    # S4 dropped off entirely (cancelled). S1/S2/S3 still here, S5 new.
    today = _frame(
        [
            _row("Sarah", "S1", "WBH"),
            _row("Sarah", "S2"),
            _row("Sarah", "S3"),
            _row("Sarah", "S5", "VIP"),
        ]
    )
    cards = compute_rep_scorecards(
        today, SNAPSHOT, new_rep_threshold=1, prior_snapshot_rows=prior
    )
    sarah = next(c for c in cards if c.rep_name == "Sarah")
    # 1 of 4 prior roster (S4) gone → cancel_rate 0.25.
    assert sarah.cancelled == 1
    assert sarah.cancel_rate == 0.25
    # Durability: 3 of prior 4 (S1,S2,S3) still present & enrolled → 3/3 = 1.0
    # (S4 not in window because it's not in today's rows at all).
    assert sarah.durability_basis_count == 3
    assert sarah.durability == 1.0


def test_internal_move_not_counted_as_cancel():
    prior = _frame([_row("Sarah", "S1", cohort="UDT566")])
    # S1 moved to a different cohort but is still in the snapshot (different row).
    today = _frame([_row("Sarah", "S1", cohort="UDT568")])
    cards = compute_rep_scorecards(
        today, SNAPSHOT, new_rep_threshold=1, prior_snapshot_rows=prior
    )
    sarah = next(c for c in cards if c.rep_name == "Sarah")
    assert sarah.cancelled == 0  # still present somewhere → not a cancel
    assert sarah.cancel_rate == 0.0


def test_action_status_multitag_counts_wbh():
    rows = _frame(
        [_row("Sarah", "A", "VIP, WBH"), _row("Sarah", "B", "")]
    )
    cards = compute_rep_scorecards(rows, SNAPSHOT, new_rep_threshold=1)
    sarah = next(c for c in cards if c.rep_name == "Sarah")
    assert sarah.wbh_rate == 0.5


def test_new_rep_excluded_from_team_avg():
    rows = _frame(
        [_row("Sarah", f"S{i}", "WBH") for i in range(8)]
        + [_row("Newbie", f"N{i}", "") for i in range(2)]
    )
    cards = compute_rep_scorecards(rows, SNAPSHOT, new_rep_threshold=5)
    newbie = next(c for c in cards if c.rep_name == "Newbie")
    sarah = next(c for c in cards if c.rep_name == "Sarah")
    assert newbie.is_new_rep is True
    assert not sarah.is_new_rep
    assert "new rep" in newbie.note


def test_unassigned_rows_ignored():
    rows = _frame([_row("", "U1"), _row("Sarah", "S1")])
    cards = compute_rep_scorecards(rows, SNAPSHOT, new_rep_threshold=0)
    assert [c.rep_name for c in cards] == ["Sarah"]


def test_vs_team_avg_ranks_reps():
    rows = _frame(
        [_row("Top", f"T{i}", "WBH") for i in range(20)]
        + [_row("Mid", f"M{i}", "WBH" if i < 10 else "") for i in range(20)]
        + [_row("Bot", f"B{i}", "") for i in range(20)]
    )
    cards = compute_rep_scorecards(rows, SNAPSHOT, new_rep_threshold=2)
    by = {c.rep_name: c for c in cards}
    assert by["Top"].vs_team_avg > by["Mid"].vs_team_avg > by["Bot"].vs_team_avg
