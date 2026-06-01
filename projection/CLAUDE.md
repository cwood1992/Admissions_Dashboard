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
rep_health.py → rep scorecard (depends only on ingest, can run parallel to velocity/projections)
calibrate.py  → updates baselines/ from completed/ (only when a cohort's start date has passed)
```

**Input format (2026-05-15+):** the weekly source is a single consolidated
`raw/<date>/EnrollList.csv` (all currently-enrolled future students; schema in
`utils.ENROLL_LIST_COLUMNS`). `ingest_snapshot_dir` auto-detects it. The old
25-file per-cohort CCS format (`utils.CCS_COLUMNS`, `load_ccs_csv`) is retained
as the **booked-class calibration source** — staged in `raw/booked/` (e.g.
`raw/booked/CCS-U566.csv`) and fed via `record_actuals.py --from-ccs` once a
class starts. EnrollList has no cancellation signal, so per-rep `cancel_rate`
and durability are week-over-week derivations and ATE-to-start comes from the
booked CCS, not the weekly pull.

Dashboard reads JSON written into `dashboard/data/` by the scripts. Scripts must not embed presentation logic — the HTML layer owns rendering.

## Projection Model: Three Regimes by Time-to-Start

`projections.py` switches strategy based on `days_to_start`. This is in the spec and is load-bearing:

- **30+ days out:** enrollment distribution model (38% C / 22% C+1 / 21% C+2 / 19% C+3) projects additional enrollments, then ATE-to-start conversion rate is applied, weighted toward the cohort's position average.
- **14–30 days out:** blend accumulation projection with confidence tiers (WBH × WBH-to-start rate + VIP × VIP-to-start rate + remainder at baseline).
- **Under 14 days:** confidence tiers dominate. WBH count minus historical no-show rate is the floor; VIP × conversion is the upside.

Every projection must record its `projection_basis` so the dashboard can show *why* a number is what it is.

## Calibration Loop

When a cohort's start date passes, `calibrate.py` compares actuals against the projections that were made at 60/30/14/7 days out, then updates the files in `baselines/` (position averages, ATE-to-start rates, accumulation curves, enrollment distribution, confidence tier conversion rates). The model is explicitly **data-starved** in the first ~6 months; confidence tier conversion rates don't exist yet and have to be built up. Don't fabricate them or use overconfident defaults — frame outputs with the available-data caveat.

## Non-Obvious Constraints

These will not be evident from reading the code alone:

- **FERPA / no PII in outputs.** Snapshots, dashboards, and exported views use counts and percentages only. Student names and IDs may exist in `raw/` but must never propagate downstream.
- **Transfer chains must not double-count.** When a student cancels from cohort C and re-enrolls in cohort C+N, they appear in both raw files. The correct interpretation is: cancel in C, new enrollment in C+N — not a net loss. `ingest.py` needs to handle this.
- **Never single-point projections.** Always low/mid/high. The spec treats this as a hard rule.
- **Don't overstate model confidence.** Especially early. Phrase outputs as "based on X data points, the model projects Y," not as predictions.
- **Cohort count is configured at 10/10/5.** If a snapshot delivers a different count, `ingest.py` should flag — it may indicate a program change requiring reindex of position averages, not just a missing file.
- **New reps** (fewer than 2 completed cohort cycles) should be excluded from rep quality scoring, not scored against the team average.

## Inputs and Where They Come From

- `raw/YYYY-MM-DD/*.csv` — manual weekly STARS export, 25 files per snapshot. Future phases automate this (n8n inbox watcher, or Claude in Chrome browser automation).
- `baselines/*.csv` — seeded from historical 2022–2025 cohort data; updated by `calibrate.py`.
- Revenue figure: **$25,300 blended revenue per start** (used in projections.py year-total calculation).
- Program start dates: spec references `Master Prompt Modules/references/Program_Start_Dates_2026.md` (lives in user's Obsidian vault, not this repo).

## Implementation Phasing

Per the spec: Phase 1 is manual Claude Code orchestration (now); later phases move to Cowork scheduled tasks for autonomous weekly runs, then GitHub Pages deployment of the dashboard. Build for Phase 1 first — don't pre-optimize for Cowork or add scheduling infrastructure until called for.
