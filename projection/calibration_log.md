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

## 2026-07-07 calibration run

Cohorts processed: UDT567, NDT567

### Baseline deltas
- NDT-Day ate rate: mid 0.0790 -> 0.0812 (observed 0.0900 from NDT567, lr=0.2)
- UDT ate rate: mid 0.1278 -> 0.1164 (observed 0.0708 from UDT567, lr=0.2)
- WBH conversion: 0.7637 -> 0.6110 (observed 0.0000 from UDT567, lr=0.2)
- WBH conversion: 0.6110 -> 0.4888 (observed 0.0000 from NDT567, lr=0.2)
- VIP conversion: 0.3360 -> 0.2688 (observed 0.0000 from UDT567, lr=0.2)
- VIP conversion: 0.2688 -> 0.2150 (observed 0.0000 from NDT567, lr=0.2)
- Priority conversion: 0.2211 -> 0.1769 (observed 0.0000 from UDT567, lr=0.2)
- Priority conversion: 0.1769 -> 0.1415 (observed 0.0000 from NDT567, lr=0.2)

