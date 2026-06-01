"""PII linter for dashboard data files.

FERPA: aggregated/derived data shipped to the dashboard must never contain
student-level identifiers (IDs, names). The pipeline aggregates at the cohort
and rep level; any leak indicates a bug worth catching in CI.
"""
import json
import re
from pathlib import Path

import pytest

from scripts.utils import CCS_COLUMNS, DASHBOARD_DATA_DIR

# Keys forbidden in any dashboard JSON.
PII_FORBIDDEN_KEYS = {
    CCS_COLUMNS["student_id"],
    CCS_COLUMNS["student_name"],
    "student_id",
    "student_name",
    "Student ID",
    "Student Name",
}

# Heuristic for student-ID-shaped values.
STUDENT_ID_PATTERNS = [
    re.compile(r"^S\d{3,}$"),  # synthetic fixtures use S001 etc.
]


def _walk(obj, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v, "key"
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _scan_json_for_pii(blob) -> list[str]:
    violations: list[str] = []
    for path, key, value, kind in _walk(blob):
        if kind == "key" and key in PII_FORBIDDEN_KEYS:
            violations.append(f"forbidden key {key!r} at {path}")
        if isinstance(value, str):
            for pat in STUDENT_ID_PATTERNS:
                if pat.match(value):
                    violations.append(
                        f"value matches student-ID pattern {pat.pattern!r}: "
                        f"{value!r} at {path}.{key}"
                    )
    return violations


def _dashboard_jsons() -> list[Path]:
    if not DASHBOARD_DATA_DIR.exists():
        return []
    return sorted(DASHBOARD_DATA_DIR.glob("*.json"))


@pytest.mark.parametrize("path", _dashboard_jsons(), ids=lambda p: p.name)
def test_dashboard_json_has_no_pii(path: Path):
    blob = json.loads(path.read_text())
    violations = _scan_json_for_pii(blob)
    assert violations == [], f"PII leaked into {path}:\n  - " + "\n  - ".join(violations)


def test_linter_catches_injected_pii(tmp_path: Path):
    bad = tmp_path / "leak.json"
    bad.write_text(
        json.dumps(
            {
                "cohorts": [
                    {"cohort": "UDT566", "Student ID": "S001", "Student Name": "Real Person"},
                ]
            }
        )
    )
    violations = _scan_json_for_pii(json.loads(bad.read_text()))
    assert any("Student ID" in v for v in violations)
    assert any("Student Name" in v for v in violations)


def test_linter_catches_student_id_in_string_value(tmp_path: Path):
    # Sneakier: id-shaped value under an innocuous key name.
    bad = tmp_path / "sneaky.json"
    bad.write_text(json.dumps({"notes": "see S0042 for details"}))
    violations = _scan_json_for_pii(json.loads(bad.read_text()))
    # Match-only at start so this one shouldn't trigger.
    # We use ^...$ patterns; "see S0042 for details" doesn't match. Sanity check.
    assert violations == []
    # Now check exact-match:
    bad.write_text(json.dumps({"cohorts": [{"id": "S0042"}]}))
    violations = _scan_json_for_pii(json.loads(bad.read_text()))
    assert any("student-ID pattern" in v for v in violations)
