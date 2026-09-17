# Projection accuracy: snapshots vs actual starts

Generated 2026-09-17 by `scripts/accuracy_report.py`. Long form: `projection_accuracy.csv`.

99 projections graded: 10 cohorts (classes 566 to 569) across 18 weekly snapshots, 2026-05-12 to 2026-09-04.

## How to read this

- **Actual** is `actual_starts` from `completed/cohort_actuals.csv` (booked CCS, Active only).
- **Error** is projected mid minus actual, in starts. Positive means the model projected high.
- **In range** means low <= actual <= high for that snapshot.
- **Bias (pooled)** is sum of errors / sum of actuals; **Abs error (pooled)** is sum of absolute errors / sum of actuals. Pooling keeps 3-start cohorts from dominating a percentage.
- A cohort appears once per weekly snapshot, so rows within a cohort are not independent. The Cohorts column is the real sample size.
- Snapshots are graded as published (version pulled from git), not as later recomputed. `earliest-available` marks a snapshot whose first commit is more than 3 days after its date, so the published numbers cannot be confirmed.
- The model changed during this period (tier rates calibrated at each class start; curve and far-regime fixes on 2026-09-14). Early rows grade an earlier model.

## By days to start

| Days to start | Projections | Cohorts | Mean error | Mean abs error | Bias (pooled) | Abs error (pooled) | Actual in range | Mean range width |
|---|---|---|---|---|---|---|---|---|
| 0-7 | 13 | 10 | -0.5 | 1.7 | -5% | 17% | 46% | 2.2 |
| 8-14 | 9 | 7 | -0.7 | 3.3 | -5% | 23% | 56% | 6.3 |
| 15-30 | 16 | 7 | +0.2 | 4.6 | +1% | 34% | 50% | 8.1 |
| 31-60 | 26 | 7 | +4.9 | 5.8 | +37% | 44% | 58% | 9.5 |
| 61-90 | 23 | 5 | +3.5 | 5.3 | +26% | 40% | 61% | 8.9 |
| 91+ | 12 | 2 | +4.0 | 10.0 | +22% | 56% | 0% | 11.0 |

## By projection regime

| Regime | Projections | Cohorts | Mean error | Mean abs error | Bias (pooled) | Abs error (pooled) | Actual in range | Mean range width |
|---|---|---|---|---|---|---|---|---|
| near-<14 | 19 | 10 | -0.7 | 2.5 | -6% | 20% | 42% | 3.6 |
| medium-14-30 | 19 | 7 | +0.2 | 4.1 | +2% | 31% | 58% | 7.7 |
| far-30+ | 61 | 7 | +4.2 | 6.5 | +29% | 45% | 48% | 9.6 |

## By program

| Program | Projections | Cohorts | Mean error | Mean abs error | Bias (pooled) | Abs error (pooled) | Actual in range | Mean range width |
|---|---|---|---|---|---|---|---|---|
| NDT-Day | 42 | 4 | -1.6 | 4.0 | -11% | 29% | 40% | 6.3 |
| NDT-Night | 15 | 2 | -0.5 | 1.3 | -7% | 17% | 87% | 4.3 |
| UDT | 42 | 4 | +7.6 | 7.8 | +50% | 51% | 43% | 11.1 |

## By program and days to start

| Program @ days | Projections | Cohorts | Mean error | Mean abs error | Bias (pooled) | Abs error (pooled) | Actual in range | Mean range width |
|---|---|---|---|---|---|---|---|---|
| NDT-Day @ 0-7 | 5 | 4 | -1.4 | 2.2 | -14% | 22% | 40% | 2.2 |
| NDT-Day @ 8-14 | 4 | 3 | -3.5 | 4.5 | -22% | 29% | 25% | 5.5 |
| NDT-Day @ 15-30 | 7 | 3 | -3.7 | 4.6 | -25% | 31% | 43% | 6.4 |
| NDT-Day @ 31-60 | 11 | 3 | +0.7 | 2.9 | +5% | 21% | 64% | 7.5 |
| NDT-Day @ 61-90 | 9 | 2 | +1.0 | 4.6 | +9% | 39% | 44% | 6.8 |
| NDT-Day @ 91+ | 6 | 1 | -6.0 | 6.0 | -30% | 30% | 0% | 7.3 |
| NDT-Night @ 0-7 | 3 | 2 | -1.0 | 1.7 | -15% | 25% | 33% | 1.7 |
| NDT-Night @ 8-14 | 1 | 1 | -2.0 | 2.0 | -25% | 25% | 100% | 4.0 |
| NDT-Night @ 15-30 | 2 | 1 | -1.5 | 1.5 | -19% | 19% | 100% | 4.5 |
| NDT-Night @ 31-60 | 4 | 1 | +1.2 | 1.2 | +16% | 16% | 100% | 5.8 |
| NDT-Night @ 61-90 | 5 | 1 | -1.0 | 1.0 | -12% | 12% | 100% | 4.8 |
| UDT @ 0-7 | 5 | 4 | +0.8 | 1.2 | +6% | 9% | 60% | 2.4 |
| UDT @ 8-14 | 4 | 3 | +2.5 | 2.5 | +17% | 17% | 75% | 7.8 |
| UDT @ 15-30 | 7 | 3 | +4.6 | 5.4 | +33% | 40% | 43% | 10.9 |
| UDT @ 31-60 | 11 | 3 | +10.4 | 10.4 | +71% | 71% | 36% | 12.8 |
| UDT @ 61-90 | 9 | 2 | +8.6 | 8.6 | +47% | 47% | 56% | 13.3 |
| UDT @ 91+ | 6 | 1 | +14.0 | 14.0 | +88% | 88% | 0% | 14.7 |

## Whole class (all programs summed)

Low and high combine the cohort ranges as independent errors (mids add; the distances to low and high add in quadrature), the same rule the FY roll-up uses.

| Class | Snapshot | Days out | Low / mid / high | Actual | Error | Error % | In range |
|---|---|---|---|---|---|---|---|
| 566 | 2026-05-12 | 6 | 16.3 / 22 / 25.6 | 19 | +3 | +16% | yes |
| 566 | 2026-05-15 | 3 | 21.6 / 23 / 24.4 | 19 | +4 | +21% | no |
| 567 | 2026-05-12 | 48 | 33.6 / 40 / 47.2 | 26 | +14 | +54% | no |
| 567 | 2026-05-15 | 45 | 33.6 / 40 / 47.2 | 26 | +14 | +54% | no |
| 567 | 2026-05-22 | 38 | 32.9 / 40 / 47.8 | 26 | +14 | +54% | no |
| 567 | 2026-05-26 | 34 | 32.9 / 40 / 47.8 | 26 | +14 | +54% | no |
| 567 | 2026-06-01 | 28 | 20.6 / 27 / 32 | 26 | +1 | +4% | yes |
| 567 | 2026-06-08 | 21 | 20.9 / 28 / 35.2 | 26 | +2 | +8% | yes |
| 567 | 2026-06-12 | 17 | 24.2 / 32 / 37 | 26 | +6 | +23% | yes |
| 567 | 2026-06-18 | 11 | 22.2 / 28 / 32.2 | 26 | +2 | +8% | yes |
| 567 | 2026-06-26 | 3 | 21 / 22 / 23 | 26 | -4 | -15% | no |
| 568 | 2026-05-12 | 83 | 31.8 / 38 / 44.6 | 33 | +5 | +15% | yes |
| 568 | 2026-05-15 | 80 | 31.8 / 38 / 44.6 | 33 | +5 | +15% | yes |
| 568 | 2026-05-22 | 73 | 32.3 / 38 / 44.2 | 33 | +5 | +15% | yes |
| 568 | 2026-05-26 | 69 | 31.3 / 37 / 43.2 | 33 | +4 | +12% | yes |
| 568 | 2026-06-01 | 63 | 33.3 / 39 / 45.2 | 33 | +6 | +18% | no |
| 568 | 2026-06-08 | 56 | 32.8 / 39 / 45.2 | 33 | +6 | +18% | yes |
| 568 | 2026-06-12 | 52 | 33.8 / 40 / 46.2 | 33 | +7 | +21% | no |
| 568 | 2026-06-18 | 46 | 34.8 / 41 / 47.6 | 33 | +8 | +24% | no |
| 568 | 2026-06-26 | 38 | 34.8 / 41 / 48.1 | 33 | +8 | +24% | no |
| 568 | 2026-07-07 | 27 | 22.4 / 29 / 33.9 | 33 | -4 | -12% | yes |
| 568 | 2026-07-13 | 21 | 25.8 / 34 / 38.9 | 33 | +1 | +3% | yes |
| 568 | 2026-07-20 | 14 | 27.8 / 34 / 38.1 | 33 | +1 | +3% | yes |
| 568 | 2026-07-31 | 3 | 28.3 / 30 / 31.7 | 33 | -3 | -9% | no |
| 569 | 2026-05-12 | 119 | 32.3 / 39 / 45.7 | 36 | +3 | +8% | yes |
| 569 | 2026-05-15 | 116 | 35.4 / 43 / 50.6 | 36 | +7 | +19% | yes |
| 569 | 2026-05-22 | 109 | 34.9 / 43 / 51.1 | 36 | +7 | +19% | yes |
| 569 | 2026-05-26 | 105 | 34.9 / 43 / 51.1 | 36 | +7 | +19% | yes |
| 569 | 2026-06-01 | 99 | 39.1 / 48 / 57.8 | 36 | +12 | +33% | no |
| 569 | 2026-06-08 | 92 | 39.1 / 48 / 57.8 | 36 | +12 | +33% | no |
| 569 | 2026-06-12 | 88 | 41.1 / 50 / 60.3 | 36 | +14 | +39% | no |
| 569 | 2026-06-18 | 82 | 41.1 / 50 / 60.3 | 36 | +14 | +39% | no |
| 569 | 2026-06-26 | 74 | 41.1 / 50 / 60.3 | 36 | +14 | +39% | no |
| 569 | 2026-07-07 | 63 | 40.2 / 50 / 61.2 | 36 | +14 | +39% | no |
| 569 | 2026-07-13 | 57 | 40.2 / 50 / 61.2 | 36 | +14 | +39% | no |
| 569 | 2026-07-20 | 50 | 40.2 / 50 / 61.2 | 36 | +14 | +39% | no |
| 569 | 2026-07-31 | 39 | 40.2 / 50 / 61.2 | 36 | +14 | +39% | no |
| 569 | 2026-08-10 | 29 | 23.7 / 30 / 36.7 | 36 | -6 | -17% | yes |
| 569 | 2026-08-18 | 21 | 31.8 / 39 / 46.6 | 36 | +3 | +8% | yes |
| 569 | 2026-08-26 | 13 | 27.3 / 33 / 38.1 | 36 | -3 | -8% | yes |
| 569 | 2026-08-28 | 11 | 26.4 / 30 / 35 | 36 | -6 | -17% | no |
| 569 | 2026-09-04 | 4 | 30 / 30 / 32 | 36 | -6 | -17% | no |

## Cohort trajectories

### NDT566 (actual starts: 3)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 6 | 64 |  | 1 / 3 / 5 | 0 | +0% | yes | near-<14 | earliest-available |
| 2026-05-15 | 3 | 63 | 63 | 4 / 5 / 6 | +2 | +67% | no | near-<14 | earliest-available |

### NDT566NC (actual starts: 6)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 6 | 10 |  | 3 / 5 / 5 | -1 | -17% | no | near-<14 | earliest-available |
| 2026-05-15 | 3 | 11 | 11 | 6 / 7 / 7 | +1 | +17% | yes | near-<14 | earliest-available |

### UDT566 (actual starts: 10)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 6 | 46 |  | 9 / 14 / 17 | +4 | +40% | yes | near-<14 | earliest-available |
| 2026-05-15 | 3 | 43 | 43 | 11 / 11 / 12 | +1 | +10% | no | near-<14 | earliest-available |

### NDT567 (actual starts: 18)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 48 | 44 |  | 14 / 18 / 22 | 0 | +0% | yes | far-30+ | earliest-available |
| 2026-05-15 | 45 | 44 | 44 | 14 / 18 / 22 | 0 | +0% | yes | far-30+ | earliest-available |
| 2026-05-22 | 38 | 42 | 44 | 13 / 18 / 23 | 0 | +0% | yes | far-30+ | earliest-available |
| 2026-05-26 | 34 | 42 | 44 | 13 / 18 / 23 | 0 | +0% | yes | far-30+ | earliest-available |
| 2026-06-01 | 28 | 60 | 60 | 8 / 12 / 15 | -6 | -33% | no | medium-14-30 |  |
| 2026-06-08 | 21 | 82 | 82 | 8 / 13 / 17 | -5 | -28% | no | medium-14-30 |  |
| 2026-06-12 | 17 | 96 | 96 | 10 / 15 / 18 | -3 | -17% | yes | medium-14-30 |  |
| 2026-06-18 | 11 | 104 | 104 | 11 / 14 / 17 | -4 | -22% | no | near-<14 |  |
| 2026-06-26 | 3 | 120 | 120 | 14 / 14 / 15 | -4 | -22% | no | near-<14 |  |

### UDT567 (actual starts: 8)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 48 | 43 |  | 17 / 22 / 28 | +14 | +175% | no | far-30+ | earliest-available |
| 2026-05-15 | 45 | 44 | 44 | 17 / 22 / 28 | +14 | +175% | no | far-30+ | earliest-available |
| 2026-05-22 | 38 | 42 | 44 | 17 / 22 / 28 | +14 | +175% | no | far-30+ | earliest-available |
| 2026-05-26 | 34 | 42 | 44 | 17 / 22 / 28 | +14 | +175% | no | far-30+ | earliest-available |
| 2026-06-01 | 28 | 57 | 57 | 10 / 15 / 19 | +7 | +88% | no | medium-14-30 |  |
| 2026-06-08 | 21 | 63 | 63 | 10 / 15 / 21 | +7 | +88% | no | medium-14-30 |  |
| 2026-06-12 | 17 | 57 | 63 | 11 / 17 / 21 | +9 | +112% | no | medium-14-30 |  |
| 2026-06-18 | 11 | 49 | 63 | 9 / 14 / 17 | +6 | +75% | no | near-<14 |  |
| 2026-06-26 | 3 | 37 | 63 | 7 / 8 / 8 | 0 | +0% | yes | near-<14 |  |

### NDT568 (actual starts: 5)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 83 | 19 |  | 8 / 10 / 13 | +5 | +100% | no | far-30+ | earliest-available |
| 2026-05-15 | 80 | 19 | 19 | 8 / 10 / 13 | +5 | +100% | no | far-30+ | earliest-available |
| 2026-05-22 | 73 | 18 | 19 | 8 / 10 / 13 | +5 | +100% | no | far-30+ | earliest-available |
| 2026-05-26 | 69 | 18 | 19 | 8 / 10 / 13 | +5 | +100% | no | far-30+ | earliest-available |
| 2026-06-01 | 63 | 19 | 19 | 8 / 10 / 13 | +5 | +100% | no | far-30+ |  |
| 2026-06-08 | 56 | 20 | 20 | 8 / 10 / 13 | +5 | +100% | no | far-30+ |  |
| 2026-06-12 | 52 | 45 | 45 | 8 / 10 / 13 | +5 | +100% | no | far-30+ |  |
| 2026-06-18 | 46 | 52 | 52 | 8 / 10 / 13 | +5 | +100% | no | far-30+ |  |
| 2026-06-26 | 38 | 66 | 66 | 8 / 10 / 13 | +5 | +100% | no | far-30+ |  |
| 2026-07-07 | 27 | 63 | 66 | 4 / 6 / 8 | +1 | +20% | yes | medium-14-30 |  |
| 2026-07-13 | 21 | 104 | 104 | 4 / 7 / 9 | +2 | +40% | yes | medium-14-30 |  |
| 2026-07-20 | 14 | 117 | 117 | 4 / 7 / 9 | +2 | +40% | yes | medium-14-30 |  |
| 2026-07-31 | 3 | 123 | 123 | 4 / 5 / 6 | 0 | +0% | yes | near-<14 |  |

### NDT568NC (actual starts: 8)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 83 | 1 |  | 4 / 7 / 10 | -1 | -12% | yes | far-30+ | earliest-available |
| 2026-05-15 | 80 | 1 | 1 | 4 / 7 / 10 | -1 | -12% | yes | far-30+ | earliest-available |
| 2026-05-22 | 73 | 1 | 1 | 5 / 7 / 9 | -1 | -12% | yes | far-30+ | earliest-available |
| 2026-05-26 | 69 | 1 | 1 | 4 / 6 / 8 | -2 | -25% | yes | far-30+ | earliest-available |
| 2026-06-01 | 63 | 3 | 3 | 6 / 8 / 10 | 0 | +0% | yes | far-30+ |  |
| 2026-06-08 | 56 | 3 | 3 | 5 / 8 / 10 | 0 | +0% | yes | far-30+ |  |
| 2026-06-12 | 52 | 5 | 5 | 6 / 9 / 11 | +1 | +12% | yes | far-30+ |  |
| 2026-06-18 | 46 | 8 | 8 | 7 / 10 / 13 | +2 | +25% | yes | far-30+ |  |
| 2026-06-26 | 38 | 10 | 10 | 7 / 10 / 14 | +2 | +25% | yes | far-30+ |  |
| 2026-07-07 | 27 | 10 | 10 | 4 / 6 / 8 | -2 | -25% | yes | medium-14-30 |  |
| 2026-07-13 | 21 | 11 | 11 | 4 / 7 / 9 | -1 | -12% | yes | medium-14-30 |  |
| 2026-07-20 | 14 | 11 | 11 | 4 / 6 / 8 | -2 | -25% | yes | medium-14-30 |  |
| 2026-07-31 | 3 | 12 | 12 | 4 / 5 / 6 | -3 | -38% | no | near-<14 |  |

### UDT568 (actual starts: 20)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 83 | 27 |  | 16 / 21 / 26 | +1 | +5% | yes | far-30+ | earliest-available |
| 2026-05-15 | 80 | 29 | 29 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ | earliest-available |
| 2026-05-22 | 73 | 31 | 31 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ | earliest-available |
| 2026-05-26 | 69 | 31 | 31 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ | earliest-available |
| 2026-06-01 | 63 | 33 | 33 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ |  |
| 2026-06-08 | 56 | 38 | 38 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ |  |
| 2026-06-12 | 52 | 65 | 65 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ |  |
| 2026-06-18 | 46 | 73 | 73 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ |  |
| 2026-06-26 | 38 | 89 | 89 | 16 / 21 / 26 | +1 | +5% | yes | far-30+ |  |
| 2026-07-07 | 27 | 87 | 89 | 11 / 17 / 21 | -3 | -15% | yes | medium-14-30 |  |
| 2026-07-13 | 21 | 93 | 93 | 13 / 20 / 24 | 0 | +0% | yes | medium-14-30 |  |
| 2026-07-20 | 14 | 94 | 94 | 16 / 21 / 24 | +1 | +5% | yes | medium-14-30 |  |
| 2026-07-31 | 3 | 74 | 94 | 19 / 20 / 21 | 0 | +0% | yes | near-<14 |  |

### NDT569 (actual starts: 20)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 119 | 2 |  | 11 / 14 / 17 | -6 | -30% | no | far-30+ | earliest-available |
| 2026-05-15 | 116 | 2 | 2 | 11 / 14 / 17 | -6 | -30% | no | far-30+ | earliest-available |
| 2026-05-22 | 109 | 2 | 2 | 10 / 14 / 18 | -6 | -30% | no | far-30+ | earliest-available |
| 2026-05-26 | 105 | 2 | 2 | 10 / 14 / 18 | -6 | -30% | no | far-30+ | earliest-available |
| 2026-06-01 | 99 | 2 | 2 | 10 / 14 / 18 | -6 | -30% | no | far-30+ |  |
| 2026-06-08 | 92 | 2 | 2 | 10 / 14 / 18 | -6 | -30% | no | far-30+ |  |
| 2026-06-12 | 88 | 6 | 6 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-06-18 | 82 | 6 | 6 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-06-26 | 74 | 8 | 8 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-07-07 | 63 | 12 | 12 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-07-13 | 57 | 17 | 17 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-07-20 | 50 | 35 | 35 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-07-31 | 39 | 75 | 75 | 12 / 16 / 21 | -4 | -20% | yes | far-30+ |  |
| 2026-08-10 | 29 | 87 | 87 | 8 / 10 / 13 | -10 | -50% | no | medium-14-30 |  |
| 2026-08-18 | 21 | 235 | 235 | 11 / 15 / 18 | -5 | -25% | no | medium-14-30 |  |
| 2026-08-26 | 13 | 255 | 255 | 10 / 14 / 15 | -6 | -30% | no | near-<14 |  |
| 2026-08-28 | 11 | 228 | 255 | 12 / 14 / 18 | -6 | -30% | no | near-<14 |  |
| 2026-09-04 | 4 | 144 | 255 | 15 / 15 / 17 | -5 | -25% | no | near-<14 |  |

### UDT569 (actual starts: 16)

| Snapshot | Days out | Enrolled | High water | Low / mid / high | Error | Error % | In range | Regime | Version |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 119 | 3 |  | 19 / 25 / 31 | +9 | +56% | no | far-30+ | earliest-available |
| 2026-05-15 | 116 | 4 | 4 | 22 / 29 / 36 | +13 | +81% | no | far-30+ | earliest-available |
| 2026-05-22 | 109 | 4 | 4 | 22 / 29 / 36 | +13 | +81% | no | far-30+ | earliest-available |
| 2026-05-26 | 105 | 4 | 4 | 22 / 29 / 36 | +13 | +81% | no | far-30+ | earliest-available |
| 2026-06-01 | 99 | 6 | 6 | 26 / 34 / 43 | +18 | +112% | no | far-30+ |  |
| 2026-06-08 | 92 | 7 | 7 | 26 / 34 / 43 | +18 | +112% | no | far-30+ |  |
| 2026-06-12 | 88 | 16 | 16 | 26 / 34 / 43 | +18 | +112% | no | far-30+ |  |
| 2026-06-18 | 82 | 19 | 19 | 26 / 34 / 43 | +18 | +112% | no | far-30+ |  |
| 2026-06-26 | 74 | 26 | 26 | 26 / 34 / 43 | +18 | +112% | no | far-30+ |  |
| 2026-07-07 | 63 | 30 | 30 | 25 / 34 / 44 | +18 | +112% | no | far-30+ |  |
| 2026-07-13 | 57 | 29 | 30 | 25 / 34 / 44 | +18 | +112% | no | far-30+ |  |
| 2026-07-20 | 50 | 61 | 61 | 25 / 34 / 44 | +18 | +112% | no | far-30+ |  |
| 2026-07-31 | 39 | 71 | 71 | 25 / 34 / 44 | +18 | +112% | no | far-30+ |  |
| 2026-08-10 | 29 | 83 | 83 | 14 / 20 / 26 | +4 | +25% | yes | medium-14-30 |  |
| 2026-08-18 | 21 | 118 | 118 | 18 / 24 / 31 | +8 | +50% | no | medium-14-30 |  |
| 2026-08-26 | 13 | 115 | 118 | 15 / 19 / 24 | +3 | +19% | yes | near-<14 |  |
| 2026-08-28 | 11 | 95 | 118 | 13 / 16 / 19 | 0 | +0% | yes | near-<14 |  |
| 2026-09-04 | 4 | 56 | 118 | 15 / 15 / 15 | -1 | -6% | no | near-<14 |  |

## Snapshots recomputed after publication

The grading above uses the published column.

| Snapshot | Cohort | Days out | Published low / mid / high | Recomputed low / mid / high | Actual | Published error | Recomputed error |
|---|---|---|---|---|---|---|---|
| 2026-09-04 | NDT569 | 4 | 15 / 15 / 17 | 15 / 16 / 18 | 20 | -5 | -4 |
| 2026-09-04 | UDT569 | 4 | 15 / 15 / 15 | 15 / 15 / 16 | 16 | -1 | -1 |
