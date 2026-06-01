# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Unified Strategic Dashboard — repository layout

This repo is the home of a **unified strategic dashboard** built from two engines plus a join layer. Both engines stay independent; a dark **shell** hosts them and a **ledger** joins their outputs by cohort code.

```
admissions_dashboard/            ← git root
├─ shell/                        ← unified dark entry point (NEW)
│  ├─ index.html                 ← top-nav: Historical | Projections | Cash (stub)
│  └─ assets/theme.css           ← canonical dark palette — single source of truth (:root tokens)
├─ index.html, process_ccs.py    ← HISTORICAL engine (backward-looking start-rate analysis)
│  summary_*.csv, summary_index.json, leads.csv, CCS_Raw/
├─ projection/                   ← FORWARD engine (cohort-fill projection pipeline, uv-managed)
│  ├─ scripts/, tests/, baselines/, completed/cohort_actuals.csv
│  ├─ raw/ (GITIGNORED — student PII, FERPA), snapshots/
│  └─ dashboard/                 ← projection's own dark dashboard (reads dashboard/data/*.json)
└─ ledger/                       ← canonical join layer (cash foundation, NEW)
   ├─ build_ledger.py            ← joins both engines' OUTPUTS by cohort code
   ├─ cohort_ledger.json         ← generated: per-cohort lifecycle + booked/projected revenue
   └─ cohort_ledger.schema.json
```

- **Two engines, one repo.** `projection/` keeps its own `uv` / `pyproject.toml` island and is run with `uv`. The historical engine uses ambient `python` + pandas. They do **not** share a venv. Only `ledger/build_ledger.py` reaches across both, and it reads their *output files*, never their internals.
- **Theme.** `shell/assets/theme.css` is the only place the dark palette is defined. Both `index.html` and `projection/dashboard/index.html` link it; do not reintroduce a second `:root` block.
- **Shell hosts via iframes.** Each dashboard runs unmodified inside its own document so its relative `fetch()` paths keep working. Serve from the repo **root** so the iframe `../` paths resolve.
- **The two "start" definitions are both correct and intentional** (do not "fix" this): the historical engine counts `Active+Drop+Grad` (its CCS pulls land long after start), while the projection engine counts `Active` only (its booked pulls land right at start). See `ledger/build_ledger.py` `reconciliation_warnings`.

### Unified run workflow (PowerShell, from repo root)

```powershell
cd projection; uv sync; .\weekly.ps1                       # 1. forward projections (drop EnrollList.csv)
cd ..; python process_ccs.py CCS_Raw\2026\ --year 2026     # 2. historical summary
python ledger\build_ledger.py                              # 3. build the canonical cohort ledger
python -m http.server 8000                                 # 4. serve from ROOT
# open http://localhost:8000/shell/index.html
```

`ledger/build_ledger.py` runs under ambient `python` (needs pandas); it imports `program_for_cohort` / `position_for_cohort` / `REVENUE_PER_START` from `projection/scripts/`. The Cash Position tab is stubbed but not yet built — see the plan/`cohort_ledger.schema.json` for the prorated-revenue design.

The projection engine has its own detailed guide at `projection/CLAUDE.md`.

---

## Historical engine (index.html + process_ccs.py)

The rest of this file documents the historical dashboard specifically.

### Running it standalone

The dashboard fetches CSV files at runtime and requires a local server (cannot open via `file://`). It is normally viewed through the shell, but can be opened directly:

```bash
# Option A — Python
python -m http.server 8000
# Then open http://localhost:8000/index.html   (or .../shell/index.html for the unified view)

# Option B — VS Code Live Server
# Right-click index.html → "Open with Live Server"
```

Requires internet connection — Chart.js is loaded from CDN. The dark theme comes from `shell/assets/theme.css` (linked in the `<head>`) plus a dark-override block at the end of the `<style>` section; per-rep chart colors stay in the `COLORS` array.

## Processing CCS Data

```bash
# Single-year mode (writes summary.csv)
python process_ccs.py

# Multi-year mode (writes summary_YEAR.csv, updates summary_index.json)
python process_ccs.py CCS_Raw/2024/ --year 2024
python process_ccs.py CCS_Raw/2025/ --year 2025
python process_ccs.py CCS_Raw/2026/ --year 2026
```

Requires `pip install pandas`.

## Architecture

### Data Flow

```
STARS CCS exports (CSV) → process_ccs.py → summary_YEAR.csv
                                          → summary_index.json

leads.csv (manual) ─────────────────────────────────────┐
summary_index.json → index.html (fetch) → rawData[]     │
summary_YEAR.csv   →                   → leadsData{}  ──┘
                                        → processData()
                                        → updateDashboard()
```

### Key Files

- **`index.html`** — The entire dashboard: all HTML, CSS, and JavaScript in one self-contained file. No build step, no bundler.
- **`process_ccs.py`** — Python script that reads raw STARS CCS exports and writes aggregated summary CSVs.
- **`summary_index.json`** — Auto-generated manifest listing per-year summary files. Do not edit manually.
- **`leads.csv`** — Manual entry: lead counts by rep for funnel charts. Supports optional `_period_` metadata row.
- **`CCS_Raw/YEAR/`** — Drop raw STARS CCS export files here before running `process_ccs.py`.

### Metrics

| Metric | Definition |
|--------|------------|
| Enrollments | All students ever scheduled for the cohort |
| Starts | Students with status Active, Drop, or Grad (re-enrollments excluded) |
| Start Rate | Starts / Enrollments * 100 |

### process_ccs.py Internals

- `HEADER_ROWS_TO_SKIP = 6` — STARS exports have 6 metadata rows before column headers.
- `START_STATUSES = {'Active', 'Drop', 'Grad'}` — statuses that count as "started".
- `extract_program()` maps cohort names to program types: NDT, UDT, NDT-NC, UDT-NC (based on prefix and NC suffix).
- Deduplicates records by `ID` + `CCS Cohort` when an ID column is present.
- Required CSV columns: `Lead Rep`, `CCS Cohort`, `CCS Status`, `Enroll Type`.

### index.html Structure

The JS is organized in clearly marked sections (search for `// ====`):

1. **CONFIG** (~line 385) — `COLORS`, `EXCLUDED_REPS`, `MIN_REP_THRESHOLD`, `REP_START_COHORT`, `REP_TARGETS`, `REP_START_TARGETS`, `PROGRAM_TARGET`, `PROG_LABELS`.
2. **STATE** (~line 426) — Global mutable state: `rawData`, `leadsData`, `availableYears`, `selectedYears`, `selectedRepsFilter`, `activeReps`, `repColorMap`, `processedData`, `charts`, `currentChartType`, `leadsPeriod`.
3. **UTILITIES** (~line 443) — `extractCohortNumber`, `destroyChart`, `getRepColor`, `rollingAvg`, `isAllReps`, `getSingleRep`, `getFilteredReps`.
4. **LOAD DATA** (~line 478) — `loadData()`: fetches `summary_index.json`, then each year CSV, then `leads.csv`. Falls back to `summary.csv` if no index.
5. **CONTROLS INIT** (~line 554) — `initControls()`: year checkboxes, cohort range sliders, program filter, rep chip listener, chart type buttons.
6. **DATA PROCESSING** (~line 615) — `processData()`: filters `rawData` by active years/cohort range, calls `detectActiveReps()`, builds `processedData` keyed by program.
7. **DASHBOARD ORCHESTRATOR** (~line 798) — `updateDashboard()`: calls all chart/section update functions for each program.
8. **Chart update functions** (~line 817–1695) — One function per section: `updateSummaryBar`, `updateRepScorecards`, `updateProgramProgressBar`, `updateTrendsChart`, `updateYOYChart`, `updateCrossYearChart`, `updateVolumeChart`, `updateTotalsAndComparison`, `updateCompositionChart`, `updateFunnelChart`, `updateDataTable`.
9. **START** (~line 1697) — Entry point: calls `loadData()`.

### Rep Filtering

`selectedRepsFilter` is a `Set<string>` — empty means "All Reps". Helper functions:
- `isAllReps()` — true when set is empty
- `getSingleRep()` — returns the rep name if exactly one is selected, else null
- `getFilteredReps()` — returns the subset of `activeReps` matching `selectedRepsFilter` (or all if none selected)

Rep chip UI is built by `buildRepFilterChips()` and toggled via `toggleRepChip(rep)`. If all reps are individually selected, it collapses back to "All".

### Multi-Year Support

`selectedYears` (a `Set`) controls which year files are active. Year checkboxes are shown only when multiple years are loaded. The YOY and Cross-Year charts use `processedData._yearData` keyed by program then year.

### Cohort Identification

Cohort names follow the pattern `NDT560`, `UDT562`, `NDT562NC`. `extractCohortNumber()` pulls the numeric portion for sorting and range filtering.

### Config Values to Update Regularly

In the `// CONFIG` section of `index.html`:
- `REP_START_COHORT` — first cohort number where each rep's data is valid (exclude earlier cohorts from their stats)
- `REP_TARGETS` — per-rep start rate target (%)
- `REP_START_TARGETS` — per-rep absolute start count target for the current year (used for scorecard progress bars)
- `PROGRAM_TARGET` — program-level start rate shown when "All Reps" is selected

### leads.csv Format

```csv
Rep,Leads
_period_,Oct 2023 – Jan 2026
Cori,7500
Randy,8200
```

The `_period_` row is optional; if present, its value appears as a small label in the funnel section header. Only include reps with meaningful enrollment data.
