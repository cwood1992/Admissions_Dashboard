# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Dashboard

The dashboard fetches CSV files at runtime and requires a local server (cannot open via `file://`):

```bash
# Option A — Python
python -m http.server 8000
# Then open http://localhost:8000/index.html

# Option B — VS Code Live Server
# Right-click index.html → "Open with Live Server"
```

Requires internet connection — Chart.js is loaded from CDN.

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
