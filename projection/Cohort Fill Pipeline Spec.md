---
uid: c4e8f2a1-7b3d-4e95-9c16-8d2a5f1e3b9c
type: agent-spec
status: draft
version: '0.1'
area: Operations
created: '2026-05-06'
tags:
  - automation
  - admissions
  - modeling
  - agent-spec
---

# Agent Spec: Cohort Fill Pipeline

## Metadata

- **Status:** draft
- **Version:** 0.1
- **Background:** TOC's admissions team monitors enrollment for upcoming cohorts using a STARS query that shows currently enrolled students. This is descriptive, not predictive — it shows who's enrolled now but provides no historical baseline, no projected starts, no enrollment accumulation trends, and no predictive rep performance metrics. The Cohort Fill Pipeline adds the analytical and predictive layer on top of the existing STARS workflow, turning enrollment snapshots into start forecasts that improve with each completed cohort.
- **Trigger:** Claude Code project (Python scripts for data processing, HTML dashboard for visualization). Transition to Cowork scheduled task when available for autonomous weekly runs.
- **Inputs:** Weekly CCS CSV exports from STARS for 25 open cohorts (10 UDT, 10 NDT Day, 5 NDT Night)
- **Outputs:** Cohort health dashboard, start projections, rep pipeline metrics, management summary, model calibration updates
- **Feedback Loop:** Each completed cohort feeds actual results back to recalibrate conversion rates, enrollment accumulation curves, confidence tier reliability, and enrollment distribution percentages

## Identity

- **Role:** Enrollment pipeline analyst that transforms raw CCS snapshots into start predictions, cohort health assessments, and rep performance insights.
- **Standing Orders:**
  - Always compare current state against historical baselines — raw numbers without context are useless
  - Predictions must show a range (low/mid/high), never a single point estimate
  - Flag cohorts tracking below baseline with specific detail on what's weak (low fill, high cancel rate, few WBH, etc.)
  - Rep performance analysis focuses on pipeline quality (cancel rates, WBH conversion, pipeline durability) not just enrollment volume
  - Every prediction should state what assumptions it relies on and how confident the model is given available data
- **Constraints:**
  - No student PII in outputs (use counts and percentages, not names or IDs) — FERPA applies
  - Don't overstate model confidence early on — the system is data-starved until it has 6+ months of snapshots
  - Don't present model outputs as certainty. Frame as "based on X data points, the model projects Y"
- **Escalation:** Flag for human review when a cohort's projected starts are 50%+ below the historical position average, when a new cohort pattern has no historical precedent, or when the model's prior predictions for recently completed cohorts were off by more than 30%

## Knowledge Requirements

| Item | Type | Source | Notes |
|------|------|--------|-------|
| Cohort summary data 2022-2025 | Static (grows annually) | CSV files from STARS / admissions dashboard | Position averages, ATE-to-start rates, program trends |
| 2026 deferred revenue schedule | Static (updated periodically) | Finance / Janie | Revenue per start, monthly recognition pattern |
| CCS weekly snapshots | Dynamic | STARS export (manual CSV) | The primary input — 25 cohorts per week |
| Start model snapshots (Aug-Oct 2025) | Static | Historical reference | 8 snapshots for cohorts 558-561 with ATE and actuals |
| Program start dates 2026 | Static | `Master Prompt Modules/references/Program_Start_Dates_2026.md` | Maps cohort numbers to calendar dates |
| Enrollment distribution model | Accumulated | Derived from historical data | 38% C / 22% C+1 / 21% C+2 / 19% C+3 — recalibrates with each cohort |
| ATE-to-start conversion rates | Accumulated | Derived from completed cohorts | UDT 9-14%, NDT Day 8-16%, NDT Night ~21% — recalibrates |
| Confidence tier conversion rates | Accumulated | Built over time from WBH/VIP/P-flag outcomes | Does not exist yet — will build as snapshots accumulate |
| Cohort analysis raw findings | Static | `Projects/John Transition/Cohort Analysis Raw Findings.md` | Baseline analysis from 05/06/2026 |

## Data Architecture

### Snapshot Format

Each weekly CCS export gets processed into a standardized snapshot record. Raw CSVs are archived; aggregated metrics are the working data.

**Per-cohort snapshot metrics:**

```
snapshot_date, cohort, program, start_date, days_to_start,
total_ever_enrolled, currently_enrolled,
new_enrolled, transfer_enrolled, reenroll_enrolled,
cancelled_total, cancelled_gone, cancelled_moved_later,
wbh_count, vip_count,
p_fa_count, p_va_count, p_act_count, p_adm_count,
cold_count, new_untagged_count,
projected_starts_low, projected_starts_mid, projected_starts_high
```

**Per-rep within each snapshot:**

```
rep_name, rep_total_assigned, rep_currently_enrolled,
rep_new, rep_transfer,
rep_cancelled, rep_cancel_rate,
rep_wbh, rep_vip, rep_priority
```

### Storage Structure

```
Cohort_Pipeline/
├── scripts/                      # Python processing scripts
│   ├── ingest.py                # Parse raw CCS CSVs → aggregated snapshots
│   ├── velocity.py              # Calculate days-to-start, enrollment velocity
│   ├── projections.py           # Generate start projections (low/mid/high)
│   ├── rep_health.py            # Rep pipeline quality metrics
│   ├── calibrate.py             # Feedback loop — update baselines with actuals
│   └── utils.py                 # Shared functions (CCS parsing, date math, etc.)
├── dashboard/                    # HTML dashboard (serves all audience views)
│   ├── index.html               # Main dashboard with tab/view switching
│   ├── data/                    # JSON output from scripts, consumed by dashboard
│   └── assets/                  # CSS, JS
├── raw/                          # Archived CCS CSV exports
│   └── YYYY-MM-DD/              # One folder per snapshot date
│       ├── UDT566.csv
│       ├── NDT566.csv
│       └── ...
├── snapshots/                    # Processed aggregated metrics
│   └── YYYY-MM-DD_snapshot.csv  # All 25 cohorts in one file
├── baselines/                    # Historical reference data
│   ├── position_averages.csv    # Starts by position by program (2022-2025)
│   ├── ate_conversion_rates.csv # ATE-to-start rates by program
│   ├── accumulation_curves.csv  # Enrollment growth curves by interval
│   └── enrollment_distribution.csv
├── completed/                    # Actuals for finished cohorts (feedback loop)
│   └── cohort_actuals.csv       # Cohort, ATE, actual_starts, by-rep breakdown
├── calibration_log.md           # Model accuracy tracking over time
├── CLAUDE.md                    # Claude Code project instructions
└── README.md                    # System documentation
```

Project lives as a Claude Code project on local machine. Dashboard can be served locally or deployed to GitHub Pages alongside the existing admissions dashboard.

## Workflow

### Step 1: Ingest Weekly Snapshots

- **WHEN:** Always — this is the entry point. Triggered weekly after CCS exports are pulled from STARS.
- **INSTRUCTIONS:** Read all CCS CSV files for the current snapshot date. For each cohort file, parse the raw student-level data and compute the aggregated snapshot metrics: total ever enrolled, currently enrolled (broken out by new/transfer/reenroll), cancelled (broken out by truly gone vs moved to later cohort), and counts by confidence tier (WBH, VIP, P-FA, P-VA, P-Act, P-Adm). Count cold/untagged separately. Store the per-rep breakdown as well. Compare field count against expected 25 cohorts and flag any missing files.
- **SUCCESS CRITERIA:**
  - All 25 expected cohort files are ingested (or missing files are explicitly flagged)
  - Aggregated metrics match raw data (enrolled + cancelled = total records)
  - Per-rep totals sum to cohort totals
  - Snapshot is appended to the historical snapshot file, not overwriting prior weeks
- **RESPONSE FORMAT:** Append one row per cohort to `snapshots/YYYY-MM-DD_snapshot.csv`. Write processing summary to console/log.
- **CONFIGURATION:** Input path: `raw/YYYY-MM-DD/`. Output path: `snapshots/`.

### Step 2: Calculate Days-to-Start and Enrollment Velocity

- **WHEN:** Always, after Step 1.
- **INSTRUCTIONS:** For each cohort, calculate days to start from the snapshot date. Then compute enrollment velocity: how many new enrollments (total ever enrolled delta) since the last snapshot, and how that compares to the historical accumulation curve for this program at this days-to-start interval. The accumulation curve shows how fast cohorts typically fill — a cohort that's 60 days out with 40 enrolled might be on track if history shows most enrollment comes in the final 30 days, or it might be behind if similar cohorts had 80 at this point. The enrollment distribution model (currently 38/22/21/19% across C through C+3) informs expected additional enrollments.
- **SUCCESS CRITERIA:**
  - Days-to-start is accurate against published start dates
  - Velocity is expressed as both absolute (net new this week) and relative (vs historical rate at this interval)
  - Cohorts within 30 days of start get the most precise comparison (more historical data points at this interval)
- **RESPONSE FORMAT:** Added columns to snapshot record: `days_to_start`, `weekly_velocity`, `velocity_vs_historical` (above/below/on-track).

### Step 3: Project Starts

- **WHEN:** Always, after Step 2.
- **INSTRUCTIONS:** Generate start projections for each cohort using a layered approach based on how close the cohort is to its start date.

  **30+ days out:** Use enrollment distribution model to project additional enrollments, then apply ATE-to-start conversion rate for the program. Weight toward the cohort position average as a prior, adjusted by current fill status.

  **14-30 days out:** Blend the accumulation-based projection with the confidence tier assessment. If confidence tiers are tagged, weight them: WBH × historical WBH-to-start rate, VIP × historical VIP-to-start rate, remainder at baseline rate. If tiers aren't tagged yet, use ATE projection only.

  **Under 14 days:** Confidence tiers are the primary predictor. WBH count is the floor (minus historical no-show rate). VIP count × conversion rate is the upside. This is where rep ground-truth matters most.

  All projections produce three numbers: low (conservative — assumes no improvement from current state), mid (base — applies historical conversion rates), and high (optimistic — assumes favorable trends continue).

- **SUCCESS CRITERIA:**
  - Every open cohort has a low/mid/high projection
  - Projections for near-term cohorts (under 30 days) use confidence tiers when available
  - Projections state their basis (e.g., "based on position average with fill adjustment" or "based on WBH count × 90% show rate")
  - Year-total projection sums individual cohort projections
  - Revenue impact is calculated: projected starts × $25,300 blended revenue per start
- **RESPONSE FORMAT:** Added columns: `proj_low`, `proj_mid`, `proj_high`, `projection_basis`. Year summary row at bottom.

### Step 4: Assess Rep Pipeline Health

- **WHEN:** Always, after Step 1.
- **INSTRUCTIONS:** For each rep, calculate pipeline quality metrics across all their assigned students in open cohorts:

  - **Cancel rate:** What percentage of students they've enrolled have cancelled (vs moved to later cohorts vs still enrolled). Compare against team average.
  - **WBH conversion:** Of students they enrolled, what percentage have reached WBH status? Higher is better — it means their enrollments are progressing toward commitment.
  - **Pipeline durability:** Of students they enrolled 60+ days ago, what percentage are still enrolled vs cancelled? Reps who enroll students that stick have durable pipelines.
  - **Enrollment quality score:** Composite of the above, indexed to team average (100 = average, above = better pipeline quality).

  This is predictive, not descriptive. A rep with 30 enrollments but a 60% cancel rate is producing fewer starts than a rep with 20 enrollments and 30% cancel rate. Surface this before the class books so Thomas can coach.

- **SUCCESS CRITERIA:**
  - Every active rep has metrics calculated
  - Metrics are compared against team average (not absolute standards)
  - Reps with significantly below-average pipeline quality are flagged
  - Metrics improve in accuracy as more snapshots accumulate (early snapshots will have wide confidence intervals)
- **RESPONSE FORMAT:** Rep scorecard table: `rep_name, total_assigned, currently_enrolled, cancel_rate, wbh_rate, durability, quality_score, vs_team_avg`.

### Step 5: Generate Audience-Specific Views

- **WHEN:** Always, after Steps 3 and 4.
- **INSTRUCTIONS:** Produce four outputs from the same underlying data:

  **Thomas View (Weekly Operations):**
  Cohort-by-cohort table showing: cohort, days to start, currently enrolled, WBH/VIP/Priority counts, projected starts (low/mid/high), vs historical average, status flag (green/yellow/red). Below that, rep scorecard from Step 4. Flag specific cohorts needing attention and why.

  **Rep View (Pipeline Focus):**
  Per-rep breakdown of their students across upcoming cohorts. Highlights students needing action: untagged (need assessment), Priority flags (need cross-department follow-up), students enrolled 30+ days with no tier advancement.

  **Clanton View (Strategic):**
  Year-to-date actual starts vs projection. Full-year projected starts by scenario. Revenue impact. Comparison to prior year at same point. Model confidence level. Feeds pro forma.

  **Management View (Headline):**
  Three numbers: projected year-end starts (mid case), vs target, and vs last year. One-paragraph narrative on trajectory. Any red-flagged cohorts called out in one sentence each.

- **SUCCESS CRITERIA:**
  - Each view contains only information relevant to its audience
  - Thomas view is actionable at the cohort and rep level
  - Management view fits in one screen / one email
  - No student PII in any view
- **RESPONSE FORMAT:** Markdown for vault/email distribution. Could also render as HTML dashboard artifact.

### Step 6: Calibrate Model (Feedback Loop)

- **WHEN:** When a cohort's start date has passed and actual starts are known.
- **INSTRUCTIONS:** For each newly completed cohort, compare actual results against the model's projections at each snapshot interval. Record:

  - Final ATE vs projected ATE at 60/30/14/7 days out
  - Actual starts vs projected starts at each interval
  - WBH-to-start conversion rate (what % of WBH students actually started)
  - VIP-to-start conversion rate
  - ATE-to-start rate for this cohort (adds to program baseline)
  - Rep-level: which reps' enrolled students actually started at what rate

  Update the baseline files:
  - Recalculate position averages with the new cohort included
  - Update ATE-to-start conversion rate ranges by program
  - Update enrollment distribution percentages if they've shifted
  - Update confidence tier conversion rates (WBH, VIP)
  - Log model accuracy to calibration log

  The calibration log tracks how the model's accuracy changes over time. Early predictions will be rough. As the system accumulates data, projections should tighten. If they don't, something in the model structure needs revisiting.

- **SUCCESS CRITERIA:**
  - Every completed cohort's actuals are recorded in `completed/cohort_actuals.csv`
  - Baseline files are updated with new data point
  - Calibration log shows prediction accuracy trend
  - If model error is consistently >30% for a program, flag for human review of model assumptions
- **RESPONSE FORMAT:** Updated baseline CSVs. Calibration log entry in markdown.

## Escalation Scenarios

- Cohort projected starts 50%+ below position average with under 30 days to start → flag to Clanton and Thomas with specific diagnosis
- Model predictions for last 3 completed cohorts were off by 30%+ in the same direction → model may be systematically biased, flag for review
- A rep's cancel rate exceeds 2x team average across 3+ cohorts → flag to Thomas for coaching conversation
- Zero WBH students in a cohort under 21 days from start → immediate flag, this cohort may produce zero starts

## Known Edge Cases

- **First 6 months:** Model is data-starved. Confidence tier conversion rates don't exist yet. Lean heavily on position averages and ATE-to-start rates from historical data. State uncertainty explicitly.
- **New reps:** Pipeline quality metrics have no baseline. Exclude from quality scoring until they've been through at least 2 cohort cycles.
- **Cohort number changes:** If TOC adds or removes cohorts per year, position averages need reindexing. The system should detect if the number of cohorts changes from the expected 10/10/5.
- **Seasonal anomalies:** COVID, hurricanes, regulatory disruptions can make historical baselines misleading. The model should allow manual override of position averages for specific cohorts with documented reasoning.
- **Transfer chains:** Students who cancel from one cohort and move to another appear in multiple CCS reports. The system must not double-count — a student in UDT566 who cancels and moves to UDT568 should be counted as a cancel in 566 and a new enrollment in 568, not as a loss.

## Implementation Path

### Runtime Architecture

This is a **Claude Code project** — Python scripts handle all data processing, and an HTML dashboard serves the views. Claude Code orchestrates script execution, interprets results, and generates narrative summaries. All processing logic lives in inspectable, version-controlled Python files, not in prompt chains.

Transition path: Claude Code (manual trigger) → Cowork scheduled task (autonomous weekly runs once Cowork is on machine).

### Phase 1: Claude Code Project (Now)

- Set up project structure with scripts/, dashboard/, raw/, baselines/
- Build Python scripts: ingest.py, velocity.py, projections.py, rep_health.py, calibrate.py
- Seed baselines/ from the historical analysis already completed (position averages, ATE rates)
- Build HTML dashboard with four audience views (Thomas, reps, Clanton, management)
- Scripts output JSON to dashboard/data/ — dashboard reads and renders
- Weekly manual CCS export from STARS (25 files dropped into raw/YYYY-MM-DD/)
- Claude Code runs the pipeline: `python scripts/ingest.py && python scripts/velocity.py` etc.
- Target: operational within 2 weeks

### Phase 2: Semi-Automated Collection (Month 2-3)

- Contact STARS vendor about automated email exports of CCS queries on a schedule
- If available: n8n watches inbox, extracts CSV attachments, drops into raw/
- If not: explore Claude in Chrome for browser automation of STARS exports
- Begin accumulating confidence tier conversion data

### Phase 3: Cowork Transition (When Available)

- Move to Cowork scheduled task for autonomous weekly runs
- Cowork reads raw/ folder, runs Python pipeline, updates dashboard/data/
- Produces weekly summary email/vault note for management
- Human reviews flagged items only

### Phase 4: Lead Data Integration (Month 4-6)

- Connect LeadSquared data upstream of enrollment
- Extend prediction window: lead → enrollment → WBH → start
- Map lead source and rep to eventual start outcome
- This turns the funnel model from enrollment-to-start into lead-to-start

### Phase 5: Self-Service Dashboard (Month 6+)

- Deploy dashboard to GitHub Pages (extend existing admissions dashboard or standalone)
- Thomas and reps can check without requiring Claude invocation
- Model has enough data for confidence tier calibration

## Next Steps

1. Initialize Claude Code project with folder structure and CLAUDE.md
2. Build Python scripts (ingest → velocity → projections → rep_health → calibrate)
3. Seed baseline files from existing cohort analysis
4. Build HTML dashboard with four audience views
5. Pull the first weekly snapshot (25 CCS exports) and run through the pipeline
6. Contact STARS vendor about automated exports
7. After 4-6 completed cohorts, first calibration review
