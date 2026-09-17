"""Projection accuracy report: every published snapshot vs booked actual starts.

For each completed cohort in completed/cohort_actuals.csv that has weekly
snapshot coverage, lines up every projection (low/mid/high) made before the
class started against ``actual_starts`` and writes:

    reports/projection_accuracy.md    tables (trajectories + summaries)
    reports/projection_accuracy.csv   long form, one row per cohort x snapshot

Snapshots are graded AS PUBLISHED. A snapshot CSV that was recomputed later
(a model fix replayed over an old date) would otherwise grade the fixed model
with hindsight, so the version is pulled from git: the last commit made within
``PUBLISHED_GRACE_DAYS`` of the snapshot date. Rows where the working file
differs from the published one are listed in their own table.

Aggregates only (counts per cohort) -- no student rows are read or written.

    uv run python -m scripts.accuracy_report
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import error_bands, utils

REPORTS_DIR = utils.PROJECT_ROOT / "reports"
REPORT_MD = "projection_accuracy.md"
REPORT_CSV = "projection_accuracy.csv"

# A snapshot committed within this many days of its date is "as published";
# a later commit to the same file is treated as a recompute.
PUBLISHED_GRACE_DAYS = 3

# Days-to-start buckets for the horizon summary (inclusive bounds; None = open).
HORIZON_BUCKETS: list[tuple[int, int | None]] = [
    (0, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, None),
]
REGIME_ORDER = ["near-<14", "medium-14-30", "far-30+"]

VERSION_PUBLISHED = "published"
VERSION_EARLIEST = "earliest-available"
VERSION_WORKING = "working-file"

LONG_COLUMNS = [
    "class_number", "cohort", "program", "snapshot_date", "days_to_start",
    "regime", "currently_enrolled", "high_water_enrolled",
    "proj_low", "proj_mid", "proj_high", "actual_starts",
    "error", "abs_error", "pct_error", "in_range", "range_width",
    "version", "version_commit", "version_commit_date",
]


@dataclass(frozen=True)
class SnapshotVersion:
    frame: pd.DataFrame
    status: str
    commit: str = ""
    commit_date: str = ""


# --------------------------------------------------------------------------
# Snapshot loading (as published)
# --------------------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def _commits_for(path: Path) -> list[tuple[str, date]]:
    """(commit, author date) for every commit touching ``path``, oldest first."""
    out = _git(["log", "--format=%H %as", "--", path.name], cwd=path.parent)
    if not out:
        return []
    commits = []
    for line in out.strip().splitlines():
        sha, day = line.split()
        commits.append((sha, date.fromisoformat(day)))
    commits.reverse()
    return commits


def load_published_snapshot(
    path: Path, snapshot_date: date, grace_days: int = PUBLISHED_GRACE_DAYS
) -> SnapshotVersion:
    """The snapshot as it stood when published, falling back to the earliest
    committed version, then to the working file when git has nothing."""
    commits = _commits_for(path)
    if not commits:
        return SnapshotVersion(pd.read_csv(path), VERSION_WORKING)
    cutoff = snapshot_date + timedelta(days=grace_days)
    in_grace = [c for c in commits if c[1] <= cutoff]
    (sha, day), status = (
        (in_grace[-1], VERSION_PUBLISHED) if in_grace
        else (commits[0], VERSION_EARLIEST)
    )
    text = _git(["show", f"{sha}:./{path.name}"], cwd=path.parent)
    if text is None:
        return SnapshotVersion(pd.read_csv(path), VERSION_WORKING)
    return SnapshotVersion(pd.read_csv(io.StringIO(text)), status, sha[:7], day.isoformat())


# --------------------------------------------------------------------------
# Long-form rows
# --------------------------------------------------------------------------

def _class_number(cohort: str) -> int | None:
    m = re.search(r"(\d+)", cohort)
    return int(m.group(1)) if m else None


def _regime(basis: object) -> str:
    text = "" if pd.isna(basis) else str(basis)
    return text.split(":", 1)[0].strip() or "unknown"


def _opt_int(row: pd.Series, col: str) -> int | None:
    if col not in row or pd.isna(row[col]):
        return None
    return int(round(float(row[col])))


def grade_snapshot(
    frame: pd.DataFrame, snapshot_date: date, actuals: dict[str, int]
) -> list[dict]:
    """One graded row per completed cohort still ahead of its start date."""
    rows = []
    for _, r in frame.iterrows():
        cohort = r["cohort"]
        if cohort not in actuals or pd.isna(r.get("proj_mid")):
            continue
        days = int(r["days_to_start"])
        if days < 0:
            continue
        low, mid, high = (float(r["proj_low"]), float(r["proj_mid"]), float(r["proj_high"]))
        actual = actuals[cohort]
        err = mid - actual
        rows.append({
            "class_number": _class_number(cohort),
            "cohort": cohort,
            "program": r["program"],
            "snapshot_date": snapshot_date.isoformat(),
            "days_to_start": days,
            "regime": _regime(r.get("projection_basis")),
            "currently_enrolled": _opt_int(r, "currently_enrolled"),
            "high_water_enrolled": _opt_int(r, "high_water_enrolled"),
            "proj_low": low,
            "proj_mid": mid,
            "proj_high": high,
            "actual_starts": actual,
            "error": err,
            "abs_error": abs(err),
            "pct_error": (err / actual) if actual else None,
            "in_range": bool(low <= actual <= high),
            "range_width": high - low,
        })
    return rows


def load_actuals(completed_dir: Path | None = None) -> dict[str, int]:
    path = (completed_dir or utils.COMPLETED_DIR) / "cohort_actuals.csv"
    df = pd.read_csv(path)
    df = df[pd.notna(df["actual_starts"])]
    return {r.cohort: int(r.actual_starts) for r in df.itertuples()}


def build_long(
    snapshots_dir: Path | None = None,
    completed_dir: Path | None = None,
    use_git: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(graded rows, recompute differences). ``use_git=False`` grades the
    working files as they are (tests, or a checkout without history)."""
    actuals = load_actuals(completed_dir)
    graded: list[dict] = []
    diffs: list[dict] = []
    for snap_date, path in utils.list_snapshots(snapshots_dir):
        version = (
            load_published_snapshot(path, snap_date) if use_git
            else SnapshotVersion(pd.read_csv(path), VERSION_WORKING)
        )
        rows = grade_snapshot(version.frame, snap_date, actuals)
        for row in rows:
            row.update(version=version.status, version_commit=version.commit,
                       version_commit_date=version.commit_date)
        graded.extend(rows)
        if version.status != VERSION_WORKING:
            current = {r["cohort"]: r for r in grade_snapshot(pd.read_csv(path), snap_date, actuals)}
            for row in rows:
                now = current.get(row["cohort"])
                if now is None:
                    continue
                if any(now[c] != row[c] for c in ("proj_low", "proj_mid", "proj_high")):
                    diffs.append({
                        "snapshot_date": row["snapshot_date"],
                        "cohort": row["cohort"],
                        "days_to_start": row["days_to_start"],
                        "published": _fmt_range(row),
                        "recomputed": _fmt_range(now),
                        "actual_starts": row["actual_starts"],
                        "published_error": row["error"],
                        "recomputed_error": now["error"],
                    })
    long = pd.DataFrame(graded, columns=LONG_COLUMNS)
    if len(long):
        long = long.sort_values(["class_number", "cohort", "snapshot_date"]).reset_index(drop=True)
    return long, pd.DataFrame(diffs)


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------

def horizon_label(days: int) -> str:
    for lo, hi in HORIZON_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return f"{lo}+" if hi is None else f"{lo}-{hi}"
    return "unknown"


def summarize(long: pd.DataFrame, by: str, order: list[str] | None = None) -> pd.DataFrame:
    """Error summary per group. WAPE and bias are pooled over the group's rows
    (sum of errors / sum of actuals) so small cohorts do not dominate."""
    out = []
    for key, g in long.groupby(by, sort=False):
        total_actual = g["actual_starts"].sum()
        out.append({
            by: key,
            "projections": len(g),
            "cohorts": g["cohort"].nunique(),
            "mean_error": g["error"].mean(),
            "mean_abs_error": g["abs_error"].mean(),
            "bias_pct": g["error"].sum() / total_actual if total_actual else None,
            "wape": g["abs_error"].sum() / total_actual if total_actual else None,
            "in_range_share": g["in_range"].mean(),
            "mean_range_width": g["range_width"].mean(),
        })
    df = pd.DataFrame(out)
    if order and len(df):
        order = order + [k for k in df[by] if k not in order]
        df[by] = pd.Categorical(df[by], categories=order, ordered=True)
        df = df.sort_values(by).reset_index(drop=True)
        df[by] = df[by].astype(str)
    return df


def class_totals(long: pd.DataFrame, actuals: dict[str, int]) -> pd.DataFrame:
    """Per class x snapshot: combined cohort projections vs summed actuals. Only
    snapshots carrying every booked cohort of the class are graded."""
    booked: dict[int, set[str]] = {}
    for cohort in actuals:
        booked.setdefault(_class_number(cohort), set()).add(cohort)
    out = []
    for (num, snap), g in long.groupby(["class_number", "snapshot_date"]):
        if set(g["cohort"]) != booked.get(num, set()):
            continue
        actual = int(g["actual_starts"].sum())
        low, mid, high = error_bands.combine_independent(
            zip(g["proj_low"], g["proj_mid"], g["proj_high"])
        )
        out.append({
            "class_number": num,
            "snapshot_date": snap,
            "days_to_start": int(g["days_to_start"].min()),
            "cohorts": len(g),
            "proj_low": low, "proj_mid": mid, "proj_high": high,
            "actual_starts": actual,
            "error": mid - actual,
            "pct_error": (mid - actual) / actual if actual else None,
            "in_range": bool(low <= actual <= high),
        })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------

def _num(v, signed: bool = False) -> str:
    if v is None or pd.isna(v):
        return ""
    f = float(v)
    spec = ".0f" if abs(f - round(f)) < 1e-9 else ".1f"
    if signed and round(f, 1) != 0:
        spec = "+" + spec
    return format(f, spec)


def _pct(v, signed: bool = False) -> str:
    if v is None or pd.isna(v):
        return ""
    return f"{float(v) * 100:+.0f}%" if signed else f"{float(v) * 100:.0f}%"


def _fmt_range(row) -> str:
    return f"{_num(row['proj_low'])} / {_num(row['proj_mid'])} / {_num(row['proj_high'])}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return lines + [""]


def _summary_table(df: pd.DataFrame, by: str, label: str) -> list[str]:
    rows = [[
        str(r[by]), str(r["projections"]), str(r["cohorts"]),
        "0.0" if round(r["mean_error"], 1) == 0 else f"{r['mean_error']:+.1f}",
        f"{r['mean_abs_error']:.1f}", _pct(r["bias_pct"], signed=True), _pct(r["wape"]),
        _pct(r["in_range_share"]), f"{r['mean_range_width']:.1f}",
    ] for _, r in df.iterrows()]
    return _table(
        [label, "Projections", "Cohorts", "Mean error", "Mean abs error",
         "Bias (pooled)", "Abs error (pooled)", "Actual in range", "Mean range width"],
        rows,
    )


def render_markdown(long: pd.DataFrame, diffs: pd.DataFrame, actuals: dict[str, int]) -> str:
    today = date.today().isoformat()
    lines = [
        "# Projection accuracy: snapshots vs actual starts",
        "",
        f"Generated {today} by `scripts/accuracy_report.py`. Long form: `{REPORT_CSV}`.",
        "",
    ]
    if long.empty:
        return "\n".join(lines + ["No completed cohort has snapshot coverage yet.", ""])

    snaps = long["snapshot_date"].nunique()
    lines += [
        f"{len(long)} projections graded: {long['cohort'].nunique()} cohorts "
        f"(classes {long['class_number'].min()} to {long['class_number'].max()}) "
        f"across {snaps} weekly snapshots, {long['snapshot_date'].min()} to "
        f"{long['snapshot_date'].max()}.",
        "",
        "## How to read this",
        "",
        "- **Actual** is `actual_starts` from `completed/cohort_actuals.csv` (booked CCS, Active only).",
        "- **Error** is projected mid minus actual, in starts. Positive means the model projected high.",
        "- **In range** means low <= actual <= high for that snapshot.",
        "- **Bias (pooled)** is sum of errors / sum of actuals; **Abs error (pooled)** is sum of "
        "absolute errors / sum of actuals. Pooling keeps 3-start cohorts from dominating a percentage.",
        "- A cohort appears once per weekly snapshot, so rows within a cohort are not independent. "
        "The Cohorts column is the real sample size.",
        "- Snapshots are graded as published (version pulled from git), not as later recomputed. "
        f"`{VERSION_EARLIEST}` marks a snapshot whose first commit is more than "
        f"{PUBLISHED_GRACE_DAYS} days after its date, so the published numbers cannot be confirmed.",
        "- The model changed during this period (tier rates calibrated at each class start; "
        "curve and far-regime fixes on 2026-09-14). Early rows grade an earlier model.",
        "",
    ]

    lines += ["## By days to start", ""]
    long = long.assign(horizon=long["days_to_start"].map(horizon_label))
    order = [f"{lo}+" if hi is None else f"{lo}-{hi}" for lo, hi in HORIZON_BUCKETS]
    lines += _summary_table(summarize(long, "horizon", order), "horizon", "Days to start")

    lines += ["## By projection regime", ""]
    lines += _summary_table(summarize(long, "regime", REGIME_ORDER), "regime", "Regime")

    lines += ["## By program", ""]
    lines += _summary_table(summarize(long, "program"), "program", "Program")

    lines += ["## By program and days to start", ""]
    combo = long.assign(group=long["program"] + " @ " + long["horizon"])
    combo_order = [f"{p} @ {h}" for p in sorted(long["program"].unique()) for h in order]
    lines += _summary_table(summarize(combo, "group", combo_order), "group", "Program @ days")

    totals = class_totals(long, actuals)
    if len(totals):
        lines += [
            "## Whole class (all programs summed)", "",
            "Low and high combine the cohort ranges as independent errors (mids add; the "
            "distances to low and high add in quadrature), the same rule the FY roll-up uses.", "",
        ]
        rows = [[
            str(r["class_number"]), r["snapshot_date"], str(r["days_to_start"]),
            _fmt_range(r), str(r["actual_starts"]), _num(r["error"], signed=True),
            _pct(r["pct_error"], signed=True), "yes" if r["in_range"] else "no",
        ] for _, r in totals.iterrows()]
        lines += _table(
            ["Class", "Snapshot", "Days out", "Low / mid / high", "Actual", "Error", "Error %", "In range"],
            rows,
        )

    lines += ["## Cohort trajectories", ""]
    for cohort, g in long.groupby("cohort", sort=False):
        actual = int(g["actual_starts"].iloc[0])
        lines += [f"### {cohort} (actual starts: {actual})", ""]
        rows = [[
            r["snapshot_date"], str(r["days_to_start"]),
            _num(r["currently_enrolled"]), _num(r["high_water_enrolled"]),
            _fmt_range(r), _num(r["error"], signed=True), _pct(r["pct_error"], signed=True),
            "yes" if r["in_range"] else "no", r["regime"],
            "" if r["version"] == VERSION_PUBLISHED else r["version"],
        ] for _, r in g.sort_values("snapshot_date").iterrows()]
        lines += _table(
            ["Snapshot", "Days out", "Enrolled", "High water", "Low / mid / high",
             "Error", "Error %", "In range", "Regime", "Version"],
            rows,
        )

    lines += ["## Snapshots recomputed after publication", ""]
    if diffs.empty:
        lines += ["None of the graded rows differ from the current snapshot files.", ""]
    else:
        lines += ["The grading above uses the published column.", ""]
        rows = [[
            r["snapshot_date"], r["cohort"], str(r["days_to_start"]), r["published"],
            r["recomputed"], str(r["actual_starts"]),
            _num(r["published_error"], signed=True), _num(r["recomputed_error"], signed=True),
        ] for _, r in diffs.iterrows()]
        lines += _table(
            ["Snapshot", "Cohort", "Days out", "Published low / mid / high",
             "Recomputed low / mid / high", "Actual", "Published error", "Recomputed error"],
            rows,
        )

    return "\n".join(lines)


def write_report(
    out_dir: Path | None = None,
    snapshots_dir: Path | None = None,
    completed_dir: Path | None = None,
    use_git: bool = True,
) -> tuple[Path, Path, pd.DataFrame]:
    out_dir = out_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    long, diffs = build_long(snapshots_dir, completed_dir, use_git=use_git)
    md_path, csv_path = out_dir / REPORT_MD, out_dir / REPORT_CSV
    md_path.write_text(
        render_markdown(long, diffs, load_actuals(completed_dir)), encoding="utf-8"
    )
    long.to_csv(csv_path, index=False)
    return md_path, csv_path, long


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--no-git", action="store_true",
                        help="grade the working snapshot files instead of the published versions")
    args = parser.parse_args()
    md_path, csv_path, long = write_report(use_git=not args.no_git)
    print(f"Graded {len(long)} projections across {long['cohort'].nunique() if len(long) else 0} cohorts.")
    print(f"  {md_path}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()
