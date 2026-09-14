# Calibration log

## 2026-05-13 calibration run

Cohorts processed: NDT522, NDT522NC, NDT523, NDT524, NDT524NC, NDT525, NDT526, NDT526NC, NDT527, NDT528, NDT528NC, NDT529, NDT530, NDT530NC, NDT531, UDT522, UDT523, UDT524, UDT525, UDT526, UDT527, UDT528, UDT529, UDT530, UDT531, NDT532, NDT532NC, NDT533, NDT534, NDT534NC, NDT535, NDT536, NDT536NC, NDT537, NDT538, NDT538NC, NDT539, NDT540, NDT540NC, NDT541, UDT532, UDT533, UDT534, UDT535, UDT536, UDT537, UDT538, UDT539, UDT540, UDT541, NDT542, NDT542NC, NDT543, NDT544, NDT544NC, NDT545, NDT546, NDT546NC, NDT547, NDT548, NDT548NC, NDT549, NDT550, NDT550NC, NDT551, UDT542, UDT543, UDT544, UDT545, UDT546, UDT547, UDT548, UDT549, UDT550, UDT551, NDT552, NDT552NC, NDT553, NDT554, NDT554NC, NDT555, NDT556, NDT556NC, NDT557, NDT558, NDT558NC, NDT559, NDT560, NDT560NC, NDT561, UDT552, UDT553, UDT554, UDT555, UDT556, UDT557, UDT558, UDT559, UDT560, UDT561, NDT562, NDT562NC, NDT563, NDT564, NDT564NC, NDT565, UDT562, UDT563, UDT564, UDT565

### Model accuracy
- NDT-Day: 44 cohorts, empirical ate-to-start mean = 0.0911
- NDT-Night: 22 cohorts, empirical ate-to-start mean = 0.1828
- UDT: 44 cohorts, empirical ate-to-start mean = 0.1331

### Baseline deltas
- NDT-Day ate range: [0.0655, 0.0911, 0.1063] from n=44 cohorts (replaced placeholder)
- NDT-Night ate range: [0.1088, 0.1828, 0.25] from n=22 cohorts (replaced placeholder)
- UDT ate range: [0.0984, 0.1331, 0.1621] from n=44 cohorts (replaced placeholder)

## 2026-05-26 calibration run

Cohorts processed: UDT566, NDT566, NDT566NC

(Two earlier runs on 2026-05-26 were superseded:
1. First run used a broken start-detection rule —
   `FULL Current Status == "Active Earning"` — which counted transfer-outs
   still earning in other cohorts as starts. Fixed: now requires
   `CCS Status == "Active"`.
2. Second run did not filter REENROLLs. Per Clanton, REENROLLs are previously-
   dropped students returning and should not count as fresh pipeline starts
   (affects NDT566NC only this round).
Baselines were reset to pre-566 values for this third run; deltas below are
the authoritative values.)

### Baseline deltas
- NDT-Day ate rate: mid 0.0911 -> 0.0790 (observed 0.0306 from NDT566, lr=0.2)
- NDT-Night ate rate: mid 0.1828 -> 0.2320 (observed 0.4286 from NDT566NC, lr=0.2)
- UDT ate rate: mid 0.1331 -> 0.1278 (observed 0.1064 from UDT566, lr=0.2)
- WBH conversion: 0.9000 -> 0.8629 (observed 0.7143 from UDT566, lr=0.2)
- WBH conversion: 0.8629 -> 0.7403 (observed 0.2500 from NDT566, lr=0.2)
- WBH conversion: 0.7403 -> 0.7637 (observed 0.8571 from NDT566NC, lr=0.2)
- VIP conversion: 0.5000 -> 0.4000 (observed 0.0000 from UDT566, lr=0.2)
- VIP conversion: 0.4000 -> 0.4200 (observed 0.5000 from NDT566, lr=0.2)
- VIP conversion: 0.4200 -> 0.3360 (observed 0.0000 from NDT566NC, lr=0.2)
- Priority conversion: 0.3000 -> 0.2764 (observed 0.1818 from UDT566, lr=0.2)
- Priority conversion: 0.2764 -> 0.2211 (observed 0.0000 from NDT566, lr=0.2)

## 2026-07-07 — superseded

The first 2026-07-07 run auto-derived 567 tier conversions from the booked CCS
and recorded them as 0/N (WBH 0.7637->0.4888, VIP 0.336->0.215, Priority
0.2211->0.1415). This was wrong: a student's **Action Status is cleared once
they show/start**, so in a booked CCS the WBH/VIP/Priority flags survive only on
the no-shows — the flag-and-started cross-tab is structurally ~0. Baselines were
reset to their pre-567 values and 567 was re-recorded from the at-start
(2026-06-26) snapshot with WBH corrected by hand; see the run below.

## 2026-07-07 calibration run

Cohorts processed: UDT567, NDT567

### Baseline deltas
- NDT-Day ate rate: mid 0.0790 -> 0.0812 (observed 0.0900 from NDT567, lr=0.2)
- UDT ate rate: mid 0.1278 -> 0.1164 (observed 0.0708 from UDT567, lr=0.2)
- WBH conversion: 0.7637 -> 0.7665 (observed 0.7778 from UDT567, lr=0.2)
- WBH conversion: 0.7665 -> 0.8132 (observed 1.0000 from NDT567, lr=0.2)

## 2026-08-10 calibration run

Cohorts processed: UDT568, NDT568, NDT568NC

### Baseline deltas
- NDT-Day ate rate: mid 0.0812 -> 0.0692 (observed 0.0214 from NDT568, lr=0.2)
- NDT-Night ate rate: mid 0.2320 -> 0.2745 (observed 0.4444 from NDT568NC, lr=0.2)
- UDT ate rate: mid 0.1164 -> 0.1193 (observed 0.1307 from UDT568, lr=0.2)
- WBH conversion: 0.8132 -> 0.8245 (observed 0.8696 from UDT568, lr=0.2)
- WBH conversion: 0.8245 -> 0.8196 (observed 0.8000 from NDT568, lr=0.2)
- WBH conversion: 0.8196 -> 0.8557 (observed 1.0000 from NDT568NC, lr=0.2)
- VIP conversion: 0.3360 -> 0.2688 (observed 0.0000 from UDT568, lr=0.2)
- VIP conversion: 0.2688 -> 0.2150 (observed 0.0000 from NDT568, lr=0.2)
- VIP conversion: 0.2150 -> 0.2220 (observed 0.2500 from NDT568NC, lr=0.2)
- Priority conversion: 0.2211 -> 0.2269 (observed 0.2500 from UDT568, lr=0.2)
- Priority conversion: 0.2269 -> 0.2482 (observed 0.3333 from NDT568, lr=0.2)
- Priority conversion: 0.2482 -> 0.3985 (observed 1.0000 from NDT568NC, lr=0.2)

## 2026-09-14 calibration run

Cohorts processed: UDT569, NDT569

### Baseline deltas
- NDT-Day ate rate: mid 0.0692 -> 0.0663 (observed 0.0548 from NDT569, lr=0.2)
- UDT ate rate: mid 0.1193 -> 0.1129 (observed 0.0874 from UDT569, lr=0.2)
- WBH conversion: 0.8557 -> 0.8610 (observed 0.8824 from UDT569, lr=0.2)
- WBH conversion: 0.8610 -> 0.8771 (observed 0.9412 from NDT569, lr=0.2)
- VIP conversion: 0.2220 -> 0.2776 (observed 0.5000 from UDT569, lr=0.2)
- VIP conversion: 0.2776 -> 0.2721 (observed 0.2500 from NDT569, lr=0.2)
- Priority conversion: 0.3985 -> 0.5188 (observed 1.0000 from UDT569, lr=0.2)
- Priority conversion: 0.5188 -> 0.5650 (observed 0.7500 from NDT569, lr=0.2)

## 2026-09-14 calibration run (curves only)

Cohorts processed: UDT566, NDT566, NDT566NC

### Model accuracy
- UDT566 7d projection: 14 -> actual 10 (error +40.0%)
- NDT566 7d projection: 3 -> actual 3 (error +0.0%)
- NDT566NC 7d projection: 5 -> actual 6 (error -16.7%)

### Baseline deltas
- NDT-Day fill@7d: 0.9500 -> 0.9539 (observed mean 0.9694 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Night fill@7d: 0.9500 -> 0.9171 (observed mean 0.7857 from 1 obs, N=2 cohorts, lr=0.2)
- UDT fill@7d: 0.9500 -> 0.9600 (observed mean 1.0000 from 1 obs, N=4 cohorts, lr=0.2)

## 2026-09-14 calibration run (curves only)

Cohorts processed: UDT567, NDT567

### Model accuracy
- UDT567 30d projection: 15 -> actual 8 (error +87.5%)
- UDT567 14d projection: 17 -> actual 8 (error +112.5%)
- NDT567 30d projection: 12 -> actual 18 (error -33.3%)
- NDT567 14d projection: 15 -> actual 18 (error -16.7%)

### Baseline deltas
- NDT-Day fill@14d: 0.9000 -> 0.8200 (observed mean 0.5000 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@21d: 0.7894 -> 0.7135 (observed mean 0.4100 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@28d: 0.7419 -> 0.6535 (observed mean 0.3000 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@35d: 0.6917 -> 0.5973 (observed mean 0.2200 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@42d: 0.5421 -> 0.4776 (observed mean 0.2200 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@49d: 0.4474 -> 0.4019 (observed mean 0.2200 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@14d: 0.9000 -> 0.8315 (observed mean 0.5575 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@21d: 0.7958 -> 0.7482 (observed mean 0.5575 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@28d: 0.7496 -> 0.7006 (observed mean 0.5044 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@35d: 0.6917 -> 0.6312 (observed mean 0.3894 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@42d: 0.5665 -> 0.5310 (observed mean 0.3894 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@49d: 0.4801 -> 0.4761 (observed mean 0.4602 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@30d: clamped 0.7500 -> 0.6535 (monotonicity enforcement)
- UDT fill@30d: clamped 0.7500 -> 0.7006 (monotonicity enforcement)

## 2026-09-14 calibration run (curves only)

Cohorts processed: UDT568, NDT568, NDT568NC

### Model accuracy
- UDT568 60d projection: 21 -> actual 20 (error +5.0%)
- UDT568 30d projection: 17 -> actual 20 (error -15.0%)
- UDT568 14d projection: 21 -> actual 20 (error +5.0%)
- NDT568 60d projection: 10 -> actual 5 (error +100.0%)
- NDT568 30d projection: 6 -> actual 5 (error +20.0%)
- NDT568 14d projection: 7 -> actual 5 (error +40.0%)
- NDT568NC 60d projection: 8 -> actual 8 (error +0.0%)
- NDT568NC 30d projection: 6 -> actual 8 (error -25.0%)
- NDT568NC 14d projection: 6 -> actual 8 (error -25.0%)

### Baseline deltas
- NDT-Day fill@14d: 0.8200 -> 0.7560 (observed mean 0.5000 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@21d: 0.7135 -> 0.6597 (observed mean 0.4444 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@28d: 0.6535 -> 0.5792 (observed mean 0.2821 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@35d: 0.5973 -> 0.5343 (observed mean 0.2821 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@49d: 0.4019 -> 0.3630 (observed mean 0.2073 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@56d: 0.3865 -> 0.3263 (observed mean 0.0855 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@63d: 0.3700 -> 0.3122 (observed mean 0.0812 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@70d: 0.2572 -> 0.2220 (observed mean 0.0812 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@77d: 0.1793 -> 0.1597 (observed mean 0.0812 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@84d: 0.1276 -> 0.1191 (observed mean 0.0855 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Night fill@14d: 0.9000 -> 0.8422 (observed mean 0.6111 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@21d: 0.8019 -> 0.7637 (observed mean 0.6111 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@28d: 0.7530 -> 0.7135 (observed mean 0.5556 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@35d: 0.6917 -> 0.6644 (observed mean 0.5556 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@49d: 0.5163 -> 0.4853 (observed mean 0.3611 from 2 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@56d: 0.4310 -> 0.3781 (observed mean 0.1667 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@63d: 0.3700 -> 0.3293 (observed mean 0.1667 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@70d: 0.2699 -> 0.2270 (observed mean 0.0556 from 2 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@77d: 0.1825 -> 0.1572 (observed mean 0.0556 from 1 obs, N=2 cohorts, lr=0.2)
- NDT-Night fill@84d: 0.1264 -> 0.1122 (observed mean 0.0556 from 1 obs, N=2 cohorts, lr=0.2)
- UDT fill@14d: 0.8315 -> 0.7881 (observed mean 0.6144 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@21d: 0.7482 -> 0.7201 (observed mean 0.6078 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@28d: 0.7006 -> 0.6768 (observed mean 0.5817 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@35d: 0.6312 -> 0.6213 (observed mean 0.5817 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@49d: 0.4761 -> 0.4711 (observed mean 0.4510 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@56d: 0.4259 -> 0.3904 (observed mean 0.2484 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@63d: 0.3700 -> 0.3391 (observed mean 0.2157 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@70d: 0.2771 -> 0.2622 (observed mean 0.2026 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@77d: 0.2054 -> 0.2023 (observed mean 0.1895 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@84d: 0.1472 -> 0.1557 (observed mean 0.1895 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@30d: clamped 0.6535 -> 0.5792 (monotonicity enforcement)
- NDT-Day fill@60d: clamped 0.4000 -> 0.3263 (monotonicity enforcement)
- NDT-Night fill@30d: clamped 0.7500 -> 0.7135 (monotonicity enforcement)
- NDT-Night fill@60d: clamped 0.4000 -> 0.3781 (monotonicity enforcement)
- UDT fill@30d: clamped 0.7006 -> 0.6768 (monotonicity enforcement)
- UDT fill@60d: clamped 0.4000 -> 0.3904 (monotonicity enforcement)

## 2026-09-14 calibration run (curves only)

Cohorts processed: UDT569, NDT569

### Model accuracy
- UDT569 60d projection: 34 -> actual 16 (error +112.5%)
- UDT569 30d projection: 20 -> actual 16 (error +25.0%)
- UDT569 14d projection: 19 -> actual 16 (error +18.8%)
- UDT569 7d projection: 15 -> actual 16 (error -6.2%)
- NDT569 60d projection: 16 -> actual 20 (error -20.0%)
- NDT569 30d projection: 10 -> actual 20 (error -50.0%)
- NDT569 14d projection: 14 -> actual 20 (error -30.0%)
- NDT569 7d projection: 15 -> actual 20 (error -25.0%)

### Baseline deltas
- NDT-Day fill@7d: 0.9539 -> 0.9028 (observed mean 0.6986 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@14d: 0.7560 -> 0.7445 (observed mean 0.6986 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@21d: 0.6597 -> 0.6565 (observed mean 0.6438 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@28d: 0.5792 -> 0.5110 (observed mean 0.2384 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@42d: 0.4776 -> 0.4232 (observed mean 0.2055 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@49d: 0.3630 -> 0.3096 (observed mean 0.0959 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@56d: 0.3263 -> 0.2704 (observed mean 0.0466 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@63d: 0.3122 -> 0.2563 (observed mean 0.0329 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@77d: 0.1597 -> 0.1321 (observed mean 0.0219 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@84d: 0.1191 -> 0.0986 (observed mean 0.0164 from 1 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@91d: 0.1000 -> 0.0822 (observed mean 0.0110 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@7d: 0.9600 -> 0.8970 (observed mean 0.6448 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@14d: 0.7881 -> 0.7594 (observed mean 0.6448 from 2 obs, N=4 cohorts, lr=0.2)
- UDT fill@21d: 0.7201 -> 0.7050 (observed mean 0.6448 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@28d: 0.6768 -> 0.6322 (observed mean 0.4536 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@42d: 0.5310 -> 0.5024 (observed mean 0.3880 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@49d: 0.4711 -> 0.4435 (observed mean 0.3333 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@56d: 0.3904 -> 0.3451 (observed mean 0.1639 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@63d: 0.3391 -> 0.3041 (observed mean 0.1639 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@77d: 0.2023 -> 0.1903 (observed mean 0.1421 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@84d: 0.1557 -> 0.1453 (observed mean 0.1038 from 1 obs, N=4 cohorts, lr=0.2)
- UDT fill@91d: 0.1000 -> 0.0926 (observed mean 0.0628 from 2 obs, N=4 cohorts, lr=0.2)
- NDT-Day fill@30d: clamped 0.5792 -> 0.5110 (monotonicity enforcement)
- NDT-Day fill@35d: clamped 0.5343 -> 0.5110 (monotonicity enforcement)
- NDT-Day fill@60d: clamped 0.3263 -> 0.2704 (monotonicity enforcement)
- NDT-Day fill@90d: clamped 0.1000 -> 0.0986 (monotonicity enforcement)
- UDT fill@30d: clamped 0.6768 -> 0.6322 (monotonicity enforcement)
- UDT fill@60d: clamped 0.3904 -> 0.3451 (monotonicity enforcement)

