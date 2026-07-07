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
- **Reps** — pipeline-quality scorecards (cancel rate, WBH rate, durability, quality score).
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
(`FULL Current Status` = "Active Earning"), and the WBH/VIP/Priority
at-start-vs-started cross-tabs; you confirm; it appends to
`completed/cohort_actuals.csv`, marks the cohort's high-water row superseded,
and offers to run calibration. Calibration blends the observation into
`baselines/ate_conversion_rates.csv` and `baselines/confidence_tier_rates.csv`
(learning rate 0.2) and appends to [calibration_log.md](calibration_log.md).
Last three cohorts erring >30% same direction → escalation flag in the log.

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
