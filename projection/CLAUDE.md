# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Phase 1 is built. Pipeline runs end-to-end against synthetic fixtures. The full spec is [Cohort Fill Pipeline Spec.md](Cohort%20Fill%20Pipeline%20Spec.md) — treat it as the source of truth for design decisions. The weekly runbook lives in [README.md](README.md).

Tooling: `uv` + `pyproject.toml`. Common commands:

```powershell
uv sync                                                          # install deps
uv run pytest -q                                                 # full suite
uv run python -m scripts.run_pipeline --date 2026-05-19 --prior-date 2026-05-12
uv run python -m scripts.calibrate                               # after a cohort completes
```

## What This System Does

Weekly enrollment forecasting pipeline for TOC's admissions team. Each week, 25 CCS CSV exports (10 UDT cohorts + 10 NDT Day + 5 NDT Night) are dropped into `raw/YYYY-MM-DD/`, processed through a Python pipeline into aggregated snapshots, and surfaced through an HTML dashboard with four audience-specific views (Thomas / reps / Clanton / management).

The system is **predictive**, not descriptive. It generates start projections (always as low/mid/high ranges, never point estimates) and learns from each completed cohort via a calibration feedback loop.

## Architecture: Pipeline Order Matters

The Python scripts are a strict DAG — running them out of order produces wrong outputs because each step's columns feed the next:

```
ingest.py     → snapshots/YYYY-MM-DD_snapshot.csv (per-cohort + per-rep aggregates from raw CSVs)
high_water.py → snapshots/enrollment_high_water.csv (per-cohort peak enrollment, interim ATE denominator)
velocity.py   → adds days_to_start, weekly_velocity, velocity_vs_historical
projections.py → adds proj_low, proj_mid, proj_high, projection_basis (depends on velocity)
error_bands.py → low/high around each mid from baselines/projection_error_bands.csv (applied inside projections.project_dataframe)
rep_health.py → rep scorecard (reads raw/<date>, the raw/ snapshots ~28 and ~60 days back, and raw/booked/; independent of velocity/projections)
calibrate.py  → updates baselines/ from completed/ (only when a cohort's start date has passed)
accuracy_report.py → reports/projection_accuracy.md|.csv (every published snapshot vs actual_starts; run after a class is recorded)
```

**Input format (2026-05-15+):** the weekly source is a single consolidated
`raw/<date>/EnrollList.csv` (all currently-enrolled future students; schema in
`utils.ENROLL_LIST_COLUMNS`). `ingest_snapshot_dir` auto-detects it. The old
25-file per-cohort CCS format (`utils.CCS_COLUMNS`, `load_ccs_csv`) is retained
as the **booked-class calibration source** — staged in `raw/booked/` (e.g.
`raw/booked/CCS-U566.csv`) and fed via `record_actuals.py --from-ccs` once a
class starts. EnrollList has no cancellation signal and still lists students in
classes that already started, so `rep_health.py` scores the **forward roster
only** and derives loss/durability by classifying a 28/60-day-old roster
against today's list **and the booked CCS** (a student who started also leaves
the list; "gone" alone is not a cancel). Still listed in a class that started
14+ days ago counts as lost; under 14 days is pending and excluded (Clanton:
most savable enrollments transfer by class-start week). ATE-to-start comes
from the booked CCS, not the weekly pull. See README "Reps tab".

Dashboard reads JSON written into `dashboard/data/` by the scripts. Scripts must not embed presentation logic — the HTML layer owns rendering.

## Projection Model: Three Regimes by Time-to-Start

`projections.py` switches strategy based on `days_to_start`. This is in the spec and is load-bearing:

- **30+ days out:** accumulation curve projects final enrollment (`high_water_enrolled / expected_fill_pct`), the program's ATE-to-start mid converts it to **starts**, that is capped at 2.5x the position average and blended 1/3 with the position-average prior. Below `FAR_REGIME_MIN_FILL_PCT` (0.15, roughly 90+ days out) the position average is used alone. Units matter here: before 2026-09-14 the enrollment count was blended against the starts-denominated position average without applying ATE, so the cap always bound and every far cohort projected exactly 1.5x position average regardless of the curve.
- **14–30 days out:** blend accumulation projection with confidence tiers (WBH × WBH-to-start rate + VIP × VIP-to-start rate + remainder at baseline).
- **Under 14 days:** confidence tiers dominate. WBH count minus historical no-show rate is the floor; VIP × conversion is the upside.

The regimes own the **mid only**. Low/high are overwritten by `error_bands` (half-width = k x observed rms_z for the days-to-start bucket x sqrt(mid); k and buckets in `baselines/projection_band_config.json`), and the regime's own band is only a fallback when no table exists. The band table is measured by replaying the current model over stored snapshots and is rebuilt by `calibrate`. Roll-ups use `error_bands.combine_independent`, not sums of lows/highs. See README "Low/high bands".

Every projection must record its `projection_basis` so the dashboard can show *why* a number is what it is.

## Calibration Loop

When a cohort's start date passes, `calibrate.py` compares actuals against the projections that were made at 60/30/14/7 days out, then updates the files in `baselines/` (position averages, ATE-to-start rates, accumulation curves, enrollment distribution, confidence tier conversion rates). The model is explicitly **data-starved** in the first ~6 months; confidence tier conversion rates don't exist yet and have to be built up. Don't fabricate them or use overconfident defaults — frame outputs with the available-data caveat.

Accumulation curves are calibrated on the **high-water mark** (`high_water_enrolled / total_ever_enrolled`), never `currently_enrolled`, and `projections.py` divides the same high-water figure by the curve. The curve gate counts cohorts across all completed actuals, not just the run's pending rows (a class start delivers one cohort per program). `scripts.calibrate --cohorts ... --curves-only` replays curve calibration without touching ATE/tier rates. See README "After a class starts and books".

## Non-Obvious Constraints

These will not be evident from reading the code alone:

- **FERPA / no PII in outputs.** Snapshots, dashboards, and exported views use counts and percentages only. Student names and IDs may exist in `raw/` but must never propagate downstream.
- **Transfer chains must not double-count.** When a student cancels from cohort C and re-enrolls in cohort C+N, they appear in both raw files. The correct interpretation is: cancel in C, new enrollment in C+N — not a net loss. `ingest.py` needs to handle this.
- **Never single-point projections.** Always low/mid/high. The spec treats this as a hard rule.
- **Don't overstate model confidence.** Especially early. Phrase outputs as "based on X data points, the model projects Y," not as predictions.
- **Cohort count is configured at 10/10/5.** If a snapshot delivers a different count, `ingest.py` should flag — it may indicate a program change requiring reindex of position averages, not just a missing file.
- **New reps** (fewer than 2 completed cohort cycles) should be excluded from rep quality scoring, not scored against the team average. Implemented as a per-metric minimum sample (`MIN_METRIC_SAMPLE`), not a tenure check: a thin rate is shown with its n but left out of `vs_team_avg`.
- **Tier rates only mean something near start.** WBH tagging is 0% beyond 60 days out; rep tier progress is measured on classes 45 days or less from start. Do not reintroduce a pipeline-wide WBH rate.
- **UDT students switch to the same-class NDT cohort in week one** (day-one orientation is blunter than the reps). They show as Cancel in the booked UDT CCS and Active in the NDT CCS; `PREV Cohort` undercounts them, a student-ID join between the two booked files does not (566: 1, 569: 3). It makes UDT grade high and NDT-Day grade low near start. No switcher term is modeled.
- **Accuracy is graded on snapshots as published.** `accuracy_report.py` reads each snapshot CSV from git (last commit within 3 days of its date), not the working file, because replayed snapshots (2026-09-04 was recomputed on 2026-09-14) would grade a fixed model with hindsight. Do not "simplify" it to read `snapshots/` directly.
- **A cohort missing from `baselines/program_start_dates_2026.csv` is dropped silently** from projections, FY views and rep rosters (13 students in 576-578 were invisible until 2026-09-17). The table runs through 582; extend it each cycle.

## Inputs and Where They Come From

- `raw/YYYY-MM-DD/*.csv` — manual weekly STARS export, 25 files per snapshot. Future phases automate this (n8n inbox watcher, or Claude in Chrome browser automation).
- `baselines/*.csv` — seeded from historical 2022–2025 cohort data; updated by `calibrate.py`.
- Revenue figure: **$25,300 blended revenue per start** (used in projections.py year-total calculation).
- Program start dates: spec references `Master Prompt Modules/references/Program_Start_Dates_2026.md` (lives in user's Obsidian vault, not this repo).

## Implementation Phasing

Per the spec: Phase 1 is manual Claude Code orchestration (now); later phases move to Cowork scheduled tasks for autonomous weekly runs, then GitHub Pages deployment of the dashboard. Build for Phase 1 first — don't pre-optimize for Cowork or add scheduling infrastructure until called for.
