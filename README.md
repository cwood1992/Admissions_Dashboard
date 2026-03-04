# TOC Admissions Dashboard

Automated dashboard that reads raw STARS CCS exports and generates a self-contained HTML file with all visualizations.

## Quick Start

1. **Export CCS data from STARS** for each cohort you want to track
2. **Drop CSV files** into the `CCS_Raw/` folder
3. **Run the processor:**
   ```
   python process_ccs.py
   ```
4. **Serve the folder locally** and open `index.html` in your browser (see [Running the Dashboard](#running-the-dashboard))

## Folder Structure

```
admissions_dashboard/
├── CCS_Raw/              ← Drop raw STARS exports here
│   ├── CCS-N560.csv
│   ├── CCS-N561.csv
│   ├── CCS-U559.csv
│   └── ...
├── process_ccs.py        ← Processor script
├── index.html            ← Open via local server (see below)
├── summary.csv           ← Generated enrollment/start data
├── leads.csv             ← Manual entry: lead counts by rep
└── README.md
```

## Workflow

### Initial Setup
1. Create `CCS_Raw/` folder if it doesn't exist (script creates it)
2. Export CCS reports from STARS for desired cohorts
3. Save as CSV files (naming doesn't matter, e.g., `CCS-N560.csv`)

### Regular Updates
1. Export new/updated CCS data from STARS
2. Drop into `CCS_Raw/` (overwriting old versions is fine)
3. Run `python process_ccs.py`
4. Open/refresh `index.html` in browser

### Tip: Bookmark It
Bookmark `http://localhost:8000/index.html` (or your Live Server URL) for quick access.

## Running the Dashboard

The dashboard fetches CSV files at runtime, so it requires a local server — you can't open `index.html` directly via `file://`.

**Option A — Python (no install needed):**
```bash
cd path/to/admissions_dashboard
python -m http.server 8000
```
Then open `http://localhost:8000/index.html`

**Option B — VS Code Live Server (easiest):**
Install the [Live Server extension](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer), then right-click `index.html` → "Open with Live Server".

**Option C — GitHub Pages:**
Push the folder to a GitHub repo and enable Pages — the dashboard will be accessible at your Pages URL.

## Multi-Year Workflow

The dashboard supports loading multiple years of cohort data and comparing them side-by-side.

### Folder Structure (Multi-Year)

```
admissions_dashboard/
├── CCS_Raw/
│   ├── 2024/              ← Raw exports for 2024 cohorts
│   │   ├── CCS-N551.csv
│   │   └── ...
│   ├── 2025/              ← Raw exports for 2025 cohorts
│   │   ├── CCS-N556.csv
│   │   └── ...
│   └── 2026/              ← Raw exports for 2026 cohorts (current)
│       ├── CCS-N562.csv
│       └── ...
├── process_ccs.py
├── index.html
├── summary_2024.csv       ← Generated per-year summary files
├── summary_2025.csv
├── summary_2026.csv
├── summary_index.json     ← Auto-generated manifest (do not edit manually)
├── leads.csv
└── README.md
```

### Generating Per-Year Summary Files

Run `process_ccs.py` with the `--year` flag for each year's folder:

```bash
python process_ccs.py CCS_Raw/2024/ --year 2024
python process_ccs.py CCS_Raw/2025/ --year 2025
python process_ccs.py CCS_Raw/2026/ --year 2026
```

Each run:
- Reads all CSV files in the specified folder
- Generates `summary_YEAR.csv` with a `Year` column prepended
- Automatically updates `summary_index.json` with the new entry

The dashboard reads `summary_index.json` on load and fetches each year's CSV automatically.

### Updating a Single Year

If you get new CCS exports for an existing year, just re-run with that year's flag:

```bash
python process_ccs.py CCS_Raw/2026/ --year 2026
```

This overwrites `summary_2026.csv` and the dashboard will reflect the update on refresh.

### Single-Year Mode

If you only need one year (or are just getting started), you can still run without `--year`:

```bash
python process_ccs.py
```

This reads `CCS_Raw/` and writes `summary.csv`. The dashboard falls back to `summary.csv` automatically if `summary_index.json` is not present.

## What Gets Counted

| Metric | Definition |
|--------|------------|
| **Enrollments** | All students ever scheduled for the cohort |
| **Starts** | Students with status: Active, Drop, or Grad |
| **Start Rate** | Starts ÷ Enrollments × 100 |

## Dashboard Features

- **Program filter**: Combined (NDT + UDT), NDT Day, NDT Night, UDT
- **Year checkboxes**: Toggle individual years on/off (shown when multiple years loaded)
- **Cohort range slider**: Narrow the cohort range shown across all charts
- **Rep filter**: All reps or individual rep view
- **Chart toggle**: Line or bar chart for trends
- **Visualizations**:
  - Performance trends over time by rep (with 3-cohort rolling average)
  - Year-over-year comparison (starts by cohort position, one line per year)
  - Cross-year cohort analysis (starts per cohort slot × year, with averages and totals)
  - Rep performance scorecards (avg start rate, trend, totals, best cohort)
  - Rep comparison (horizontal bar chart of avg start rates)
  - Volume analysis (stacked enrollments/starts by cohort)
  - Enrollment composition (New / Transfer / Re-enroll breakdown)
  - Detailed data table (reps as rows, cohorts as columns)
  - Funnel charts (Leads → Enrollments → Starts, requires leads.csv)

## Troubleshooting

**Low start counts**
- Students with "Enroll" status are NOT counted as starts
- This usually means the cohort hasn't started yet OR status wasn't updated
- For cohorts already in progress, check STARS for status updates

**Missing cohort**
- Make sure you exported and dropped the CCS file for that cohort
- Re-run `python process_ccs.py`

**Charts not loading**
- Requires internet connection (loads Chart.js from CDN)
- If offline, you'd need to bundle Chart.js locally

## Requirements

- Python 3.6+ with pandas (`pip install pandas`)
- Modern browser (Chrome, Firefox, Safari, Edge)

---

## Leads Data (leads.csv)

**Manual entry required.** The dashboard reads lead counts from `leads.csv` to show full-funnel metrics (Leads → Enrollments → Starts).

### Date Range for Pulling Leads

Pull leads from your CRM using this date range:

| Boundary | Rule |
|----------|------|
| **Start date** | 15 weeks before the first cohort's start date |
| **End date** | Start date of the last cohort in summary.csv |

**Why this range:**
- The 15-week lookback (~3 cohorts) captures leads that converted into enrollments for your earliest visible cohort
- Ending at the last cohort start avoids counting leads that haven't had time to convert yet

**Example:**
If summary.csv covers cohorts 551-562:
- 551 started ~late January 2024
- 562 started ~mid January 2026
- Pull leads from **mid-October 2023** through **mid-January 2026**

### Format

```csv
Rep,Leads
Cori,7500
Randy,8200
Sue,4800
Thomas,3100
```

Only include reps tracked in the dashboard (those with 5+ enrollments in the loaded data).

### Updating Leads

1. Pull lead counts by rep from CRM for the appropriate date range
2. Update `leads.csv` with new numbers
3. Refresh dashboard (Ctrl+Shift+R to clear cache)

---

## Customization

Edit `process_ccs.py` to change:
- `START_STATUSES` — Which CCS statuses count as "started" (default: Active, Drop, Grad)
- `extract_program()` — How cohort names map to program types (NDT, UDT, NDT-NC, etc.)

Reps are detected automatically from the data — no hardcoded list needed.
