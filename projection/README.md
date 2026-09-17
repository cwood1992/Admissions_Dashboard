# Cohort Fill Pipeline

Weekly enrollment forecasting for TOC admissions. Turns 25 CCS CSV exports from STARS into per-cohort start projections (low/mid/high), rep pipeline-quality metrics, and four audience-specific dashboard views. Calibrates itself from each completed cohort.

Design spec: [Cohort Fill Pipeline Spec.md](Cohort%20Fill%20Pipeline%20Spec.md). Operating notes for future Claude Code sessions: [CLAUDE.md](CLAUDE.md).

## Weekly runbook

**One-command Friday workflow:**

```powershell
.\weekly.ps1
```

This script:
1. Creates `raw/<today>/` and opens it in Explorer.
2. Pauses for you to drop the single **`EnrollList.csv`** export in (the
   consolidated all-future-cohorts query). The legacy 25-file per-cohort format
   still works if `EnrollList.csv` is absent.
3. Runs the pipeline (ingest → high-water → projections → velocity → dashboard).
4. Lists any cohorts past their start_date that don't have actuals recorded yet.
5. Opens `dashboard/index.html` in your default browser.

Override the date if needed: `.\weekly.ps1 -Date 2026-05-15`.

**Manual equivalent** (if you'd rather call each step yourself):

```powershell
# Date arguments are optional; --date defaults to most-recent raw/ folder
# and --prior-date defaults to the most-recent snapshot before that.
uv run python -m scripts.run_pipeline
```

Four dashboard tabs:
- **Thomas · Cohorts** — operational table with velocity, projections, basis.
- **Reps** — forward pipeline per rep, tier progress in the 45-day window, 28-day loss and 60-day durability from the outcome classification, plus a rep by upcoming-class matrix. See "Reps tab" below.
- **Clanton · Strategic** — year-end roll-up with revenue.
- **Management** — three-number headline + narrative + red flags. Auto-exports markdown to `snapshots/YYYY-MM-DD_management.md` for email or vault distribution.

## After a class starts and books

The weekly `EnrollList.csv` only shows currently-enrolled future students — it
has no cancellation or who-actually-started signal. Ground-truth ATE comes from
the **booked-class CCS** (the old per-cohort export) that you pull once the
class has started and the roster is finalized.

Stage the booked CCS files in `raw/booked/` using their CCS-native names
(`CCS-U<num>.csv` for UDT, `CCS-N<num>.csv` for NDT-Day, `CCS-NNC<num>.csv`
for NDT-Night). `raw/` is gitignored so PII stays local. Then feed each cohort
in — use `--no-calibrate` on all but the last so calibration folds the whole
class in once:

```powershell
uv run python -m scripts.record_actuals UDT566   --from-ccs raw\booked\CCS-U566.csv   --no-calibrate
uv run python -m scripts.record_actuals NDT566   --from-ccs raw\booked\CCS-N566.csv   --no-calibrate
uv run python -m scripts.record_actuals NDT566NC --from-ccs raw\booked\CCS-NNC566.csv --no-calibrate
uv run python -m scripts.calibrate
```

This auto-derives `total_ever_enrolled` (row count), `actual_starts`
(`FULL Current Status` = "Active Earning"), the WBH/VIP/Priority
at-start-vs-started cross-tabs, and `proj_at_{60,30,14,7}d` (the `proj_mid`
this pipeline published in the snapshot nearest each interval before start,
within 3 days); you confirm; it appends to `completed/cohort_actuals.csv`,
marks the cohort's high-water row superseded, and offers to run calibration.
Calibration blends the observation into `baselines/ate_conversion_rates.csv`,
`baselines/confidence_tier_rates.csv` and `baselines/accumulation_curves.csv`
(learning rate 0.2) and appends to [calibration_log.md](calibration_log.md),
including a "Model accuracy" section comparing each `proj_at_*` to the actual.
Last three cohorts erring >30% same direction → escalation flag in the log.

Accumulation-curve notes:
- Observations are `high_water_enrolled / total_ever_enrolled` per weekly bin
  (not `currently_enrolled`, which collapses in the final two weeks as cancels
  are processed). `projections.py` divides the same high-water figure by the
  curve, so the two sides stay consistent.
- The per-program gate (`MIN_COHORTS_FOR_CURVE_UPDATE`, 2) counts cohorts with
  snapshot coverage across ALL completed actuals, since a class start delivers
  exactly one cohort per program.
- `--cohorts UDT568,NDT568 --curves-only` replays curve calibration for rows
  already stamped `calibrated_at` without re-blending ATE/tier rates (used on
  2026-09-14 to fold 566–569 in class by class after the gate fix).

Known gaps in `--from-ccs`: it counts rows, not students (CCS-N569 carried 10
exact-duplicate rows for 3 students), and Action Status is cleared once a
student shows, so the tier cross-tabs need the at-start EnrollList student-ID
join described in the class-start runbook. Check both before calibrating.

Without `--from-ccs` the command falls back to the fully-manual guided prompt.
The one-time historical seed (2022–2025 + early-2026) came from
`scripts/import_historical_actuals.py` against the admissions_dashboard summary
files; ongoing per-cohort ATE now comes from the booked-class CCS instead.

### Interim ATE before a class books

Because EnrollList can't give total-ever-enrolled per cohort, the pipeline
keeps a per-cohort **enrollment high-water mark** across weekly snapshots
(`snapshots/enrollment_high_water.csv`) — peak concurrent enrollment is a
close lower-bound proxy for the ATE denominator until the booked CCS supplies
the exact figure.

## Reps tab (EnrollList-native, reworked 2026-09)

`scripts/rep_health.py` no longer uses the old CCS cancel signal (EnrollList has
none). Three things to know:

- **Forward roster only.** The EnrollList still carries "Enrolled Student" rows
  for classes that already started (390 of 847 rows on 2026-09-14, back to
  UDT559). A rep's pipeline is only their students in classes that have not
  started, the same window the cohort ingest uses. `House` is excluded
  (`NON_REP_NAMES`).
- **Tier progress is measured inside the commitment window**
  (`COMMITMENT_WINDOW_DAYS = 45`). Pooled history shows WBH tagging is 0% beyond
  60 days out, so a pipeline-wide WBH rate is noise. The scored term is the
  any-tag rate (WBH, VIP or priority); the WBH rate is shown but not scored.
- **Retention is outcome-based, not "gone from the list".** Students who start
  also leave the list. The forward roster from the snapshot nearest 60 days
  back (and 28 days back for the loss rate; tolerance 10 days) is classified
  per student: `retained` (still in a future class), `started` (Active in a
  `raw/booked/` CCS), `pending` (still listed in a class that started under 14
  days ago; excluded), `lost_listed` (still listed 14+ days after that class
  started), `unknown` (gone, class started, booked CCS not staged; excluded),
  `gone`. Durable = (retained + started) / (roster - pending - unknown).

`vs Team` is the mean of each scored rate divided by the team rate (100 = team).
A rate with n under `MIN_METRIC_SAMPLE` (10) is shown but not scored; this
replaces the old "new rep under 30 students" rule. Every rate shows its n.
Because retention needs the booked CCS, stage `raw/booked/CCS-*.csv` at class
start before the weekly run or those students land in `unknown`.

The tab also shows the outcome breakdown for both lookbacks and a rep by
upcoming-class matrix (enrolled, WBH / VIP / priority, cold untagged) built
from `rep_untagged` / `rep_cold` in the per-cohort rep breakdown.

`baselines/program_start_dates_2026.csv` must cover every class students are
enrolled in: a cohort with no start date is dropped from the projection, the
FY views and the rep roster without an error. It runs through 582 (2028-01-03)
as of 2026-09-17; extend it when the next cycle's dates are set.

## Project layout

| Path | Purpose |
|------|---------|
| `scripts/` | Python pipeline (ingest → velocity → projections → rep_health → views → calibrate). |
| `baselines/` | Position averages, ATE-to-start rates, accumulation curves, distribution, tier rates. Updated by `calibrate.py`. |
| `raw/YYYY-MM-DD/` | Weekly CCS exports. **Gitignored — may contain PII.** |
| `snapshots/` | Processed per-snapshot CSVs (cohort-level + rep-level) and management markdown. |
| `completed/` | Cohort actuals for the calibration loop. |
| `dashboard/` | Vanilla HTML/CSS/JS dashboard. Reads `dashboard/data/*.js`. |
| `tests/` | pytest suite with hand-computable fixtures. |

## Tests

```powershell
uv run pytest -q          # full suite
uv run pytest tests/test_projections_regimes.py -v   # one file
```

The suite includes:
- Aggregation invariants (per-rep totals equal cohort totals; new+transfer+reenroll = currently_enrolled).
- Transfer-chain double-counting protection (a student cancelled in cohort C and re-enrolled in cohort C+N must register as cancelled-moved in C, not as cancelled-gone).
- low ≤ mid ≤ high projection ordering across all regimes and any input.
- PII linter (`tests/test_no_pii.py`) that scans every dashboard JSON for student-ID / student-name leakage — fails CI if any aggregated output contains row-level identifiers.

## Constraints (the load-bearing ones)

- **FERPA / no PII downstream.** Anything written under `dashboard/data/` or `snapshots/` is aggregated. Row-level student data lives only in `raw/`.
- **Never single-point projections.** Every cohort row reports low/mid/high; the ordering is enforced in code.
- **Data-starved framing.** Until calibration has run on several completed cohorts, `projection_basis` strings carry `[tier rates are placeholders, data-starved]` and accumulation curves stay tagged as approximate.

## Access gates

The dashboards (this one, plus the unified shell, historical, and cash engines) are
gated by a **client-side email allowlist** so not just anyone can open them and each
person sees only their assigned views. Login is email + password; on success the view
filter for that person is applied across the shell's top-nav engines and this engine's
four tabs.

**The allowlist lives in one file:** [`shell/assets/access-config.js`](../shell/assets/access-config.js)
(`window.ACCESS_USERS`). Each entry is `{ email, passwordHash, views }`. Valid view keys:
`historical`, `proj:cohorts`, `proj:reps`, `proj:strategic`, `proj:management`,
`proj:recognition`, `cash`.

**To add or change a user:**

1. Open [`tools/hash-password.html`](../tools/hash-password.html) directly in a browser
   (it runs offline — nothing is sent anywhere).
2. Type the person's email + the password you'll give them; copy the resulting hash.
3. Add/edit their entry in `access-config.js` with that `passwordHash` and the `views`
   they should see. To revoke access, delete the entry.

The shipped entries are **placeholders** (`admin@example.com` … password `changeme`).
Replace the emails and regenerate the hashes before sharing the dashboard.

### What this gate is — and isn't

This is **lane-keeping for honest users**, not real security:

- The site is static files, so anyone who view-sources or fetches
  `dashboard/data/*.js` directly can still read the aggregated numbers. Passwords are
  hashed (salted with the email) so they aren't plaintext — that raises the effort bar,
  it does not make the data secret.
- **GitHub Pages on a personal account is world-public even for a private repo.** The
  site URL and its data files are reachable by anyone who finds the address.
- **Real protection is a follow-on at the dedicated-service phase:** put the site behind
  an edge-auth layer (Cloudflare Access / Netlify Identity) or a small backend that
  authenticates and withholds the data per user. The `access-config.js` allowlist and the
  view-key vocabulary carry forward unchanged — only the identity source is swapped.

## Phasing

Per the spec: Phase 1 (this codebase) is manual orchestration on Windows. Later phases add Cowork scheduled task automation, then deploy the dashboard to GitHub Pages. Don't pre-optimize for those — they'll be follow-on work.
