# TOC Admissions Dashboard

Automated dashboard that reads raw STARS CCS exports and generates a self-contained HTML file with all visualizations.

## Quick Start

1. **Export CCS data from STARS** for each cohort you want to track
2. **Drop CSV files** into the `CCS_Raw/` folder
3. **Run the processor:**
   ```
   python process_ccs.py
   ```
4. **Open `dashboard.html`** in your browser — no server needed!

## Folder Structure

```
admissions_dashboard/
├── CCS_Raw/              ← Drop raw STARS exports here
│   ├── CCS-N560.csv
│   ├── CCS-N561.csv
│   ├── CCS-U559.csv
│   └── ...
├── process_ccs.py        ← Processor script
├── dashboard.html        ← Open via local server
├── summary.csv           ← Generated enrollment/start data
├── leads.csv             ← Manual entry: lead counts by rep
└── README.md
```

## Running the Dashboard

```bash
cd /path/to/dashboard/folder
python -m http.server 8000
```

Then open `http://localhost:8000/dashboard.html`

(Dashboard reads from CSV files, so it needs a local server—can't just open the HTML directly.)

## Workflow

### Initial Setup
1. Create `CCS_Raw/` folder if it doesn't exist (script creates it)
2. Export CCS reports from STARS for desired cohorts
3. Save as CSV files (naming doesn't matter, e.g., `CCS-N560.csv`)

### Regular Updates
1. Export new/updated CCS data from STARS
2. Drop into `CCS_Raw/` (overwriting old versions is fine)
3. Run `python process_ccs.py`
4. Open/refresh `dashboard.html` in browser

### Tip: Bookmark It
The generated HTML is fully self-contained—no server required. Bookmark `dashboard.html` for quick access.

## What Gets Counted

| Metric | Definition |
|--------|------------|
| **Enrollments** | All students ever scheduled for the cohort |
| **Starts** | Students with status: Active, Drop, or Grad |
| **Start Rate** | Starts ÷ Enrollments × 100 |

## Dashboard Features

- **Program filter**: Combined (NDT + UDT), NDT Day, NDT Night, UDT
- **Rep filter**: All reps or individual rep view
- **Chart toggle**: Line or bar chart for trends
- **Visualizations**:
  - Performance trends over time by rep
  - Rep comparison (horizontal bar)
  - Volume analysis (stacked enrollments/starts by cohort)
  - Detailed data table
- **Summary cards**: Top performer, most consistent, best cohort, program average

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

Only include the four main reps (Cori, Randy, Sue, Thomas). The dashboard filters out others automatically.

### Updating Leads

1. Pull lead counts by rep from CRM for the appropriate date range
2. Update `leads.csv` with new numbers
3. Refresh dashboard (Ctrl+Shift+R to clear cache)

---

## Customization

Edit `process_ccs.py` to change:
- `START_STATUSES` — Which statuses count as "started" (default: Active, Drop, Grad)
- `REPS` — List of sales reps to track
- `extract_program_type()` — How cohort names map to program types
