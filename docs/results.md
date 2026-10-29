# Results

Generated 2026-10-29 by `python -m eval report`. Synthetic data: these numbers show the machinery works, not that the weights hold on real data. "precise (F1)" and "broad (F2)" thresholds were tuned on the dev seed (F1 weighs precision and recall equally; F2 weighs recall about twice as much) under a hard ceiling of 50 alerts/week, and applied unchanged to the holdout seed. "@ capacity" rows use the label-free threshold that sends the most alerts without breaching the ceiling. Precision is per account unless stated.

## dev (seed 42, thresholds calibrated here)

Window 2026-06-29 → 2026-09-27 (13 weeks), 5 AEs, capacity 50/week. Thresholds (precise F1 / broad F2 / capacity): engine M2 72.52 / 35.56 / 0.55, static points 45.18 / 37.00 / 17.00, engine M1 (F1) 23.68. Active profile (what reps receive): **broad**. Positives: 25.

| Method | Alerts | Alerts/AE/week | Busiest week | Precision (alerts) | Precision (accounts) | Recall | Median lead (days) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Per-event pings | 1,084 | 16.7 | 102 | 22.8% | 7.9% | 88.0% (22/25) | 21 |
| Static points @ capacity | 185 | 2.8 | 22 | 8.6% | 8.6% | 64.0% (16/25) | 18 |
| Static points precise (F1) | 76 | 1.2 | 10 | 19.7% | 19.7% | 60.0% (15/25) | 13 |
| Static points broad (F2) | 99 | 1.5 | 11 | 18.2% | 18.2% | 72.0% (18/25) | 12 |
| Engine M1 precise (F1) | 48 | 0.7 | 6 | 58.3% | 53.6% | 60.0% (15/25) | 11 |
| Engine M2 @ capacity | 646 | 9.9 | 50 | 6.2% | 3.6% | 52.0% (13/25) | 26 |
| Engine M2 precise (F1) | 26 | 0.4 | 5 | 88.5% | 80.0% | 48.0% (12/25) | 14 |
| Engine M2 broad (F2) | 74 | 1.1 | 9 | 48.6% | 40.5% | 68.0% (17/25) | 14 |

Hand-raises routed outside scoring (demo requests): 16. Post-meeting alerts dropped from metrics: Per-event pings 4, Static points @ capacity 0, Static points precise (F1) 1, Static points broad (F2) 0, Engine M1 precise (F1) 1, Engine M2 @ capacity 2, Engine M2 precise (F1) 1, Engine M2 broad (F2) 3.

**Alerting decisions, engine M2** (cooldown 14 days, jump ×1.5, budget 2/AE/day and 10/AE/week, defer up to 3 days)

| Profile | alerted | cooldown |
|---|---:|---:|
| broad | 77 | 22 |
| precise | 27 | 2 |

**Equal alert budget** (threshold set by alert count alone; precision is per account)

| Alerts in window | Static points: precision / recall | Engine M1: precision / recall | Engine M2: precision / recall |
|---:|---:|---:|---:|
| ~15 | 0.0% / 0.0% (n=14) | 58.3% / 28.0% (n=13) | 90.0% / 36.0% (n=13) |
| ~25 | 8.7% / 8.0% (n=23) | 64.7% / 44.0% (n=23) | 80.0% / 48.0% (n=26) |
| ~40 | 10.8% / 16.0% (n=37) | 54.5% / 48.0% (n=37) | 61.9% / 52.0% (n=36) |
| ~60 | 18.3% / 44.0% (n=60) | 48.5% / 64.0% (n=57) | 51.9% / 56.0% (n=52) |

**Hard-negative accounts alerted** (distinct accounts, of those planted per type)

| Type | Planted | Per-event pings | Static points @ capacity | Static points precise (F1) | Static points broad (F2) | Engine M1 precise (F1) | Engine M2 @ capacity | Engine M2 precise (F1) | Engine M2 broad (F2) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bot_burst | 8 | 2 | 2 | 0 | 0 | 0 | 3 | 0 | 0 |
| content_binger | 8 | 3 | 6 | 6 | 6 | 3 | 7 | 1 | 2 |
| customer_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| low_fit_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| open_deal_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pricing_hammerer | 8 | 8 | 7 | 7 | 7 | 7 | 7 | 2 | 6 |
| stalled_trial | 8 | 8 | 2 | 1 | 1 | 0 | 3 | 0 | 1 |
| trigger_only | 8 | 0 | 7 | 0 | 0 | 0 | 7 | 0 | 0 |

**Positives missed by Engine M2 broad (F2) (active profile):** 8

| Account | Class | Archetype | Meeting |
|---|---|---|---|
| acc_01445 | random_converter | – | 2026-07-13 |
| acc_01798 | planted_buyer | quiet | 2026-07-21 |
| acc_00884 | random_converter | – | 2026-07-23 |
| acc_01761 | random_converter | – | 2026-07-23 |
| acc_00979 | planted_buyer | plg | 2026-08-05 |
| acc_01467 | random_converter | – | 2026-08-27 |
| acc_01869 | random_converter | – | 2026-09-14 |
| acc_01989 | planted_buyer | quiet | 2026-09-23 |

## holdout (seed 7, headline numbers)

Window 2026-06-29 → 2026-09-27 (13 weeks), 5 AEs, capacity 50/week. Thresholds (precise F1 / broad F2 / capacity): engine M2 72.52 / 35.56 / 0.55, static points 45.18 / 37.00 / 17.00, engine M1 (F1) 23.68. Active profile (what reps receive): **broad**. Positives: 25.

| Method | Alerts | Alerts/AE/week | Busiest week | Precision (alerts) | Precision (accounts) | Recall | Median lead (days) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Per-event pings | 1,149 | 17.7 | 123 | 21.6% | 7.6% | 96.0% (24/25) | 20 |
| Static points @ capacity | 179 | 2.8 | 21 | 9.5% | 9.5% | 68.0% (17/25) | 14 |
| Static points precise (F1) | 81 | 1.2 | 11 | 19.8% | 19.8% | 64.0% (16/25) | 12 |
| Static points broad (F2) | 92 | 1.4 | 15 | 20.7% | 20.7% | 76.0% (19/25) | 11 |
| Engine M1 precise (F1) | 43 | 0.7 | 6 | 58.1% | 55.6% | 60.0% (15/25) | 8 |
| Engine M2 @ capacity | 647 | 10.0 | 50 | 6.6% | 4.0% | 56.0% (14/25) | 24 |
| Engine M2 precise (F1) | 26 | 0.4 | 6 | 84.6% | 86.7% | 52.0% (13/25) | 9 |
| Engine M2 broad (F2) | 67 | 1.0 | 11 | 55.2% | 48.6% | 68.0% (17/25) | 11 |

Hand-raises routed outside scoring (demo requests): 29. Post-meeting alerts dropped from metrics: Per-event pings 12, Static points @ capacity 0, Static points precise (F1) 3, Static points broad (F2) 1, Engine M1 precise (F1) 1, Engine M2 @ capacity 2, Engine M2 precise (F1) 1, Engine M2 broad (F2) 2.

**Alerting decisions, engine M2** (cooldown 14 days, jump ×1.5, budget 2/AE/day and 10/AE/week, defer up to 3 days)

| Profile | alerted | cooldown |
|---|---:|---:|
| broad | 69 | 17 |
| precise | 27 | 3 |

**Equal alert budget** (threshold set by alert count alone; precision is per account)

| Alerts in window | Static points: precision / recall | Engine M1: precision / recall | Engine M2: precision / recall |
|---:|---:|---:|---:|
| ~15 | 6.7% / 4.0% (n=15) | 61.5% / 32.0% (n=16) | 83.3% / 40.0% (n=16) |
| ~25 | 4.2% / 4.0% (n=24) | 68.8% / 44.0% (n=23) | 86.7% / 52.0% (n=27) |
| ~40 | 15.0% / 24.0% (n=40) | 62.5% / 60.0% (n=37) | 77.8% / 56.0% (n=35) |
| ~60 | 16.9% / 40.0% (n=59) | 48.5% / 64.0% (n=60) | 54.8% / 68.0% (n=58) |

**Hard-negative accounts alerted** (distinct accounts, of those planted per type)

| Type | Planted | Per-event pings | Static points @ capacity | Static points precise (F1) | Static points broad (F2) | Engine M1 precise (F1) | Engine M2 @ capacity | Engine M2 precise (F1) | Engine M2 broad (F2) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bot_burst | 8 | 1 | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| content_binger | 8 | 2 | 6 | 8 | 7 | 2 | 7 | 0 | 0 |
| customer_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| low_fit_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| open_deal_active | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pricing_hammerer | 8 | 8 | 6 | 7 | 7 | 7 | 6 | 2 | 4 |
| stalled_trial | 8 | 8 | 0 | 1 | 0 | 0 | 4 | 0 | 1 |
| trigger_only | 8 | 0 | 6 | 0 | 0 | 0 | 8 | 0 | 0 |

**Positives missed by Engine M2 broad (F2) (active profile):** 8

| Account | Class | Archetype | Meeting |
|---|---|---|---|
| acc_01403 | random_converter | – | 2026-07-09 |
| acc_01614 | random_converter | – | 2026-07-30 |
| acc_01786 | planted_buyer | quiet | 2026-08-03 |
| acc_00246 | planted_buyer | plg | 2026-08-06 |
| acc_01317 | random_converter | – | 2026-08-12 |
| acc_01881 | random_converter | – | 2026-08-24 |
| acc_01862 | planted_buyer | quiet | 2026-08-25 |
| acc_01947 | random_converter | – | 2026-09-16 |
