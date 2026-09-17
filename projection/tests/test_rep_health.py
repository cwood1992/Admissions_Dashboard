"""Rep health tests: forward roster, commitment-window tier progress, and
outcome-based retention (EnrollList schema + booked-CCS starts)."""
from datetime import date

import pandas as pd

from scripts.rep_health import (
    classify_outcomes,
    compute_rep_scorecards,
    forward_roster,
    load_started_ids,
    pick_lookback_dir,
)
from scripts.utils import CCS_COLUMNS, ENROLL_LIST_COLUMNS, ENROLL_LIST_FILENAME

TODAY = date(2026, 9, 14)
PRIOR = date(2026, 7, 13)
C = ENROLL_LIST_COLUMNS
START = {
    "UDT568": date(2026, 8, 3),    # started 42 days before TODAY
    "UDT569": date(2026, 9, 8),    # started 6 days before TODAY
    "UDT570": date(2026, 10, 13),  # 29 days out (inside the 45-day window)
    "UDT572": date(2027, 1, 4),    # far
}


def _row(rep: str, sid: str, cohort: str = "UDT570", action: str = "", admission: str = "NEW") -> dict:
    return {
        C["admission_type"]: admission,
        C["student_id"]: sid,
        C["student_name"]: "synthetic",
        C["current_status"]: "Enroll",
        C["cohort"]: cohort,
        C["current_enroll_date"]: "2026-04-01",
        C["rep_name"]: rep,
        C["action_status"]: action,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _card(payload: dict, rep: str) -> dict:
    return next(c for c in payload["reps"] if c["rep_name"] == rep)


def test_forward_roster_drops_started_cohorts_house_and_reenrolls():
    rows = _frame(
        [
            _row("Sarah", "S1", "UDT570"),
            _row("Sarah", "S2", "UDT568"),                      # class already started
            _row("Sarah", "S3", "UDT570", admission="REENROLL"),
            _row("House", "H1", "UDT570"),
            _row("", "X1", "UDT570"),                           # unassigned
            _row("Sarah", "S4", "UDT999"),                      # not in start-date table
        ]
    )
    roster = forward_roster(rows, TODAY, START)
    assert list(roster["sid"]) == ["S1"]
    assert list(roster["days_to_start"]) == [29]


def test_tier_progress_only_counts_commitment_window():
    rows = _frame(
        [_row("Sarah", f"N{i}", "UDT570", "WBH" if i < 3 else ("VIP, P-FA" if i < 6 else "")) for i in range(12)]
        + [_row("Sarah", f"F{i}", "UDT572", "") for i in range(20)]  # far cohort: ignored for rates
    )
    sarah = _card(compute_rep_scorecards(rows, TODAY, start_dates=START), "Sarah")
    assert sarah["forward_enrolled"] == 32
    assert sarah["near_enrolled"] == 12
    assert sarah["wbh_rate_near"] == 0.25
    assert sarah["tagged_rate_near"] == 0.5
    # No lookback snapshots -> retention unavailable, never a fake number.
    assert sarah["durability"]["rate"] is None
    assert sarah["loss_rate_28d"] is None
    assert "no snapshot near 60 days back" in sarah["note"]


def test_classify_outcomes_all_buckets():
    prior = forward_roster(
        _frame(
            [
                _row("Sarah", "KEEP", "UDT570"),
                _row("Sarah", "MOVED", "UDT568"),    # transferred forward, still future
                _row("Sarah", "START", "UDT568"),    # Active in booked CCS
                _row("Sarah", "NOSHOW", "UDT568"),   # still listed in 568, started 42d ago
                _row("Sarah", "FRESH", "UDT569"),    # still listed in 569, started 6d ago
                _row("Sarah", "CANCEL", "UDT570"),   # gone, class not started
                _row("Sarah", "MAYBE", "UDT569"),    # gone, 569 booked CCS not staged
                _row("Sarah", "BEYOND", "UDT570"),   # now in a cohort past the date table
            ]
        ),
        PRIOR,
        START,
    )
    current = _frame(
        [
            _row("Sarah", "KEEP", "UDT570"),
            _row("Sarah", "MOVED", "UDT572"),
            _row("Sarah", "NOSHOW", "UDT568"),
            _row("Sarah", "FRESH", "UDT569"),
            _row("Sarah", "BEYOND", "UDT580"),
        ]
    )
    out = classify_outcomes(prior, current, TODAY, START, started_ids={"START"}, booked_cohorts={"UDT568"})
    assert dict(zip(prior["sid"], out)) == {
        "KEEP": "retained",
        "MOVED": "retained",
        "START": "started",
        "NOSHOW": "lost_listed",
        "FRESH": "pending",
        "CANCEL": "gone",
        "MAYBE": "unknown",
        "BEYOND": "retained",
    }


def test_durability_excludes_pending_and_unknown_from_denominator():
    prior_rows = _frame(
        [_row("Sarah", f"K{i}", "UDT570") for i in range(6)]      # retained
        + [_row("Sarah", f"A{i}", "UDT568") for i in range(3)]    # started
        + [_row("Sarah", f"G{i}", "UDT570") for i in range(3)]    # gone
        + [_row("Sarah", "P1", "UDT569"), _row("Sarah", "U1", "UDT569")]  # pending, unknown
    )
    current = _frame([_row("Sarah", f"K{i}", "UDT570") for i in range(6)] + [_row("Sarah", "P1", "UDT569")])
    payload = compute_rep_scorecards(
        current,
        TODAY,
        start_dates=START,
        durability_prior=(PRIOR, prior_rows),
        started_ids={"A0", "A1", "A2"},
        booked_cohorts={"UDT568"},
    )
    dur = _card(payload, "Sarah")["durability"]
    assert dur["n"] == 14
    assert dur["basis"] == 12           # 14 minus 1 pending minus 1 unknown
    assert dur["rate"] == 0.75          # (6 retained + 3 started) / 12
    assert dur["outcomes"]["pending"] == 1 and dur["outcomes"]["unknown"] == 1
    assert payload["params"]["durability_prior_date"] == "2026-07-13"


def test_vs_team_index_and_small_samples_not_scored():
    current = _frame(
        [_row("Top", f"T{i}", "UDT570", "VIP") for i in range(20)]
        + [_row("Bot", f"B{i}", "UDT570", "VIP" if i < 5 else "") for i in range(20)]
        + [_row("Tiny", f"Y{i}", "UDT570", "WBH") for i in range(3)]
    )
    payload = compute_rep_scorecards(current, TODAY, start_dates=START)
    top, bot, tiny = (_card(payload, r) for r in ("Top", "Bot", "Tiny"))
    assert top["vs_team_avg"] > 100 > bot["vs_team_avg"]
    assert top["terms_used"] == ["tagged_rate_near"]
    # Tiny's rate is reported but n=3 < 10 keeps it out of the index.
    assert tiny["tagged_rate_near"] == 1.0
    assert tiny["vs_team_avg"] is None
    assert "not scored" in tiny["note"]
    # Team rate pools every real rep: (20 + 5 + 3) / 43.
    assert payload["team"]["tagged_rate_near"] == round(28 / 43, 4)


def test_load_started_ids_dedupes_and_reads_active_only(tmp_path):
    k = CCS_COLUMNS
    booked = tmp_path / "booked"
    booked.mkdir()
    header = ",".join(f'"{v}"' for v in [k["enrollment_type"], k["student_id"], k["cohort"], k["enrollment_status"]])
    lines = [header, '"NEW","A1","UDT568","Active"', '"NEW","A1","UDT568","Active"', '"NEW","C1","UDT568","Cancel"']
    (booked / "CCS-U568.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    started, cohorts = load_started_ids(booked)
    assert started == {"A1"}
    assert cohorts == {"UDT568"}


def test_pick_lookback_dir_nearest_within_tolerance(tmp_path):
    for d in ("2026-07-13", "2026-07-20", "2026-09-04"):
        (tmp_path / d).mkdir()
        (tmp_path / d / ENROLL_LIST_FILENAME).write_text("x", encoding="utf-8")
    (tmp_path / "booked").mkdir()
    # Target 2026-07-16: 07-13 is 3 days off, 07-20 is 4.
    assert pick_lookback_dir(tmp_path, TODAY, 60)[0] == date(2026, 7, 13)
    # Target 2026-08-17: nearest is 18 days off -> outside the 10-day tolerance.
    assert pick_lookback_dir(tmp_path, TODAY, 28) is None
