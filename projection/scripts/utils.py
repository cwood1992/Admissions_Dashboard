from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "raw"
SNAPSHOTS_DIR = PROJECT_ROOT / "snapshots"
BASELINES_DIR = PROJECT_ROOT / "baselines"
COMPLETED_DIR = PROJECT_ROOT / "completed"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"

SNAPSHOT_DATE_FORMAT = "%Y-%m-%d"

# Program label by cohort-code prefix. Real CCS exports use:
#   UDT566   → UDT          (10 cohorts per year)
#   NDT566   → NDT-Day      (10 cohorts per year)
#   NDT566NC → NDT-Night    (5 cohorts per year; "NC" = Night Class)
EXPECTED_COHORT_COUNTS = {"UDT": 10, "NDT-Day": 10, "NDT-Night": 5}

# CCS column names — real STARS schema as of 2026-05-12.
CCS_COLUMNS = {
    "student_id": "ID",
    "student_name": "Student Name",
    "enrollment_type": "Enroll Type",
    "action_status": "Action Status",   # multi-valued: WBH, VIP, P-FA, ...
    "rep_name": "Lead Rep",
    "lead_origin": "Lead Origin",
    "response_mode": "Response Mode",
    "prev_cohort": "PREV Cohort",
    "prev_status": "PREV Status",
    "cohort": "CCS Cohort",              # the cohort this file is about
    "enrollment_status": "CCS Status",   # "Enroll" or "Cancel" for this cohort
    "next_cohort": "NEXT Cohort",
    "next_status": "NEXT Status",
    "current_cohort": "Current Cohort",
    "current_status": "Current Status",
    "full_student_name": "FULL Student Name",
    "full_current_status": "FULL Current Status",
}

# CCS Status values (status within THIS cohort) — old per-cohort format.
ENROLLMENT_STATUS_ENROLLED = "Enroll"
ENROLLMENT_STATUS_CANCELLED = "Cancel"
# Once a class has booked, the CCS Status flips from "Enroll" to "Active" for
# students who actually started in this cohort (whether NEW or TRANSFER-IN).
# A student "Active Earning" with CCS Status != "Active" earned in a *different*
# cohort and must not be counted as a start here.
ENROLLMENT_STATUS_ACTIVE = "Active"

# Enroll Type values.
ENROLLMENT_TYPE_NEW = "NEW"
ENROLLMENT_TYPE_TRANSFER = "TRANSFER"
ENROLLMENT_TYPE_REENROLL = "REENROLL"  # may not appear in real exports; kept for compat

# Confidence tier and priority labels (normalized).
CONFIDENCE_TIER_WBH = "WBH"
CONFIDENCE_TIER_VIP = "VIP"
PRIORITY_FLAGS = ("P-FA", "P-VA", "P-Acc", "P-Adm")

# --- Consolidated EnrollList.csv format (new weekly source, 2026-05-15+) -----
#
# One file, all currently-enrolled-in-a-future-cohort students. No metadata
# preamble. Column names per Clanton's STARS query.
ENROLL_LIST_FILENAME = "EnrollList.csv"

ENROLL_LIST_COLUMNS = {
    "admission_type": "Admission Type",
    "student_id": "ID",
    "student_name": "Student Name",
    "enroll_count": "# Enroll",
    "current_status": "Current Status",
    "cohort": "Current Cohort",
    "current_enroll_date": "Current Enroll Date",
    "prev_cohort": "Previous Cohort",
    "prev_enroll_date": "Previous Enroll Date",
    "first_cohort": "First Cohort",
    "first_enroll_date": "First Enroll Date",
    "rep_name": "Admissions Rep",
    "action_status": "Action Status",
    "lead_origin": "Lead Origin",
    "response_mode": "Response Mode",
    "status_code_description": "STATUS CODE DESCRIPTION",
}

# Current Status value for a student actively enrolled in a future cohort.
# CONFIRM on first real EnrollList pull; one-line change if it differs.
ENROLLMENT_STATUS_ENROLLED_NEW = "Enroll"

# FULL Current Status value in a booked-class CCS that means the student
# actually started. Seen alongside "Enrolled Student"/"Cancelled Enrollment"
# in the 2026-05-12 per-cohort data. CONFIRM on first real booked CCS.
STATUS_STARTED = "Active Earning"

# Untagged students enrolled longer than this (days) are "cold"; newer ones
# are "new untagged" (recently enrolled, not yet assessed).
UNTAGGED_COLD_THRESHOLD_DAYS = 14

# Weekly velocity window: a student counts toward this week's velocity if their
# current-cohort enroll date is within this many days of the snapshot. Matches
# the Friday-to-Friday pull cadence.
VELOCITY_WINDOW_DAYS = 7


def program_for_cohort(cohort_code: str) -> str:
    """Map a cohort code like 'UDT566', 'NDT566', 'NDT566NC' to program label."""
    c = cohort_code.strip().upper()
    if c.startswith("UDT"):
        return "UDT"
    if c.endswith("NC"):
        return "NDT-Night"
    if c.startswith("NDT"):
        return "NDT-Day"
    raise ValueError(f"Cannot determine program for cohort code {cohort_code!r}")


# Year-cycle anchor: cohort 562 is position 1 in each program's annual cycle.
# UDT/NDT-Day: 10 cohorts per year, numbered sequentially (562 -> 571 = pos 1-10).
# NDT-Night:    5 cohorts per year, numbered every-other (562, 564, ..., 570 = pos 1-5).
COHORT_POSITION_ANCHOR = 562
COHORTS_PER_YEAR_DAY = 10
COHORTS_PER_YEAR_NIGHT = 5
NIGHT_NUMBER_STRIDE = 2  # NDT-Night cohort numbers increment by 2 within a year


def position_for_cohort(cohort_code: str) -> int:
    """Return the 1-indexed position within the year cycle for a cohort code.

    UDT/NDT-Day cycle of 10:
        UDT562 -> 1, UDT566 -> 5, UDT571 -> 10, UDT572 -> 1 (next year), ...
    NDT-Night cycle of 5 (every-other-numbered):
        NDT562NC -> 1, NDT566NC -> 3, NDT570NC -> 5, NDT572NC -> 1, ...
    """
    c = cohort_code.strip().upper()
    if c.endswith("NC"):
        digits = "".join(ch for ch in c[:-2] if ch.isdigit())
        if not digits:
            raise ValueError(f"No cohort number in {cohort_code!r}")
        num = int(digits)
        offset = (num - COHORT_POSITION_ANCHOR) // NIGHT_NUMBER_STRIDE
        return (offset % COHORTS_PER_YEAR_NIGHT) + 1
    if c.startswith(("UDT", "NDT")):
        digits = "".join(ch for ch in c if ch.isdigit())
        if not digits:
            raise ValueError(f"No cohort number in {cohort_code!r}")
        num = int(digits)
        return ((num - COHORT_POSITION_ANCHOR) % COHORTS_PER_YEAR_DAY) + 1
    raise ValueError(f"Cannot determine position for cohort code {cohort_code!r}")


def cohort_from_filename(path: Path) -> str:
    """Recover the cohort code from a real CCS filename.

    Real CCS exports use these patterns:
      CCS-U566.csv   → UDT566
      CCS-N566.csv   → NDT566
      CCS-NNC566.csv → NDT566NC

    Empty-cohort exports have no data rows, so we can't read the cohort from
    the data — the filename is the only signal.
    """
    stem = path.stem
    if stem.startswith("CCS-"):
        stem = stem[len("CCS-"):]
    num = "".join(c for c in stem if c.isdigit())
    if not num:
        raise ValueError(f"No cohort number in filename {path.name!r}")
    if stem.startswith("NNC"):
        return f"NDT{num}NC"
    if stem.startswith("U"):
        return f"UDT{num}"
    if stem.startswith("N"):
        return f"NDT{num}"
    raise ValueError(f"Cannot recover cohort code from filename {path.name!r}")


def parse_snapshot_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, SNAPSHOT_DATE_FORMAT).date()


def list_snapshots(snapshots_dir: Path | None = None) -> list[tuple[date, Path]]:
    """Return (date, path) pairs for all snapshot CSVs, sorted ascending by date."""
    d = snapshots_dir or SNAPSHOTS_DIR
    out: list[tuple[date, Path]] = []
    if not d.exists():
        return out
    for p in d.glob("*_snapshot.csv"):
        try:
            sd = parse_snapshot_date(p.name.split("_")[0])
        except ValueError:
            continue
        out.append((sd, p))
    out.sort()
    return out


def snapshot_dir_for(snapshot_date: str | date) -> Path:
    d = parse_snapshot_date(snapshot_date)
    return RAW_DIR / d.strftime(SNAPSHOT_DATE_FORMAT)


CCS_HEADER_SIGNAL = '"Enroll Type"'  # first quoted field of the real CCS header line


def _find_header_line(path: Path) -> int:
    """Locate the 0-indexed line where the CCS data header begins.

    Real CCS exports have 4–5 metadata lines (Selected School, ..., Selected
    Cohort, optionally Total Records) followed by a blank line and the header.
    Empty cohorts skip the blank-line and Total-Records preamble.
    """
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if line.startswith(CCS_HEADER_SIGNAL):
                return i
    raise ValueError(f"No CCS header line found in {path}")


def load_ccs_csv(path: Path) -> pd.DataFrame:
    """Load a per-cohort CCS CSV (old/booked-class format), skipping preamble."""
    header_line = _find_header_line(path)
    df = pd.read_csv(path, skiprows=header_line, dtype=str, keep_default_na=False)
    # Empty-cohort exports still have the header row but zero data rows.
    return df


ENROLL_LIST_HEADER_SIGNAL = "Student Name"  # appears only in the header row


def _find_enroll_list_header(path: Path) -> int:
    """0-indexed header line. Real STARS exports have a 4-line metadata
    preamble + blank line; synthetic fixtures may have none. Either way the
    header is the first line mentioning 'Student Name'."""
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if ENROLL_LIST_HEADER_SIGNAL in line:
                return i
    raise ValueError(f"No EnrollList header found in {path}")


def load_enroll_list(path: Path) -> pd.DataFrame:
    """Load the consolidated EnrollList.csv (new weekly format).

    Skips the STARS metadata preamble, normalizes column names (STARS embeds a
    literal tab in "Admission\\tType"), all-string dtype, blank-preserving,
    values stripped so downstream comparisons are exact.
    """
    header_line = _find_enroll_list_header(path)
    df = pd.read_csv(path, skiprows=header_line, dtype=str, keep_default_na=False)
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.apply(lambda s: s.str.strip() if s.dtype == "object" else s)


# --- Action Status parser ---------------------------------------------------
#
# Real CCS Action Status is free-text and very noisy:
#   "WBH", "WBH 100%", "VIP, P-FA", "P FA", "P- Adm", "WBH 100%, P-ACC",
#   "T U567", "T-567", "VIP, T-567"
#
# We normalize each comma-separated token, strip whitespace/punctuation, and
# match against a vocabulary. Transfer markers like "T U567" / "T-567" are
# ignored here — they aren't confidence tiers or priorities.

import re as _re

_ACTION_TOKEN_SPLITTER = _re.compile(r"[,/;]")
_ACTION_TRANSFER_RE = _re.compile(r"^T[\s\-_]*[A-Z]?\d+$", _re.IGNORECASE)


def _normalize_action_token(token: str) -> str:
    """Squash spaces/dashes so 'P FA' and 'P-FA' and 'P- FA' all compare equal."""
    return _re.sub(r"[\s\-_]+", "", token).upper()


def parse_action_status(value: str | float | None) -> dict:
    """Parse a CCS Action Status cell into structured flags.

    Returns a dict with boolean fields:
        wbh, vip, p_fa, p_va, p_acc, p_adm
    plus 'raw_tokens' (the cleaned list) for diagnostic purposes.

    Unknown tokens are ignored (logged at debug level by callers if desired).
    """
    out = {"wbh": False, "vip": False, "p_fa": False, "p_va": False, "p_acc": False, "p_adm": False, "raw_tokens": []}
    if value is None:
        return out
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return out

    for raw in _ACTION_TOKEN_SPLITTER.split(s):
        token = raw.strip()
        if not token:
            continue
        out["raw_tokens"].append(token)
        if _ACTION_TRANSFER_RE.match(token):
            continue  # transfer marker, not a tier
        norm = _normalize_action_token(token)
        # WBH may be "WBH" or "WBH100%" — strip non-alnum and look for prefix.
        norm_alnum = _re.sub(r"[^A-Z0-9]", "", norm)
        if norm_alnum.startswith("WBH"):
            out["wbh"] = True
        elif norm_alnum == "VIP":
            out["vip"] = True
        elif norm_alnum in ("PFA",):
            out["p_fa"] = True
        elif norm_alnum in ("PVA",):
            out["p_va"] = True
        elif norm_alnum in ("PACC", "PACT"):  # P-Act and P-Acc both observed
            out["p_acc"] = True
        elif norm_alnum in ("PADM",):
            out["p_adm"] = True
        # else: unknown token, silently ignored
    return out
