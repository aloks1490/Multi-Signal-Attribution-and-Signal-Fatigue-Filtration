# Results

Generated 2026-10-27 by `python -m eval report`. Synthetic data: these numbers show the machinery works, not that the weights hold on real data. Deployed thresholds ("@ dev F1" and "Engine M1") were tuned for F1 on the dev seed under a hard ceiling of 50 alerts/week and applied unchanged to the holdout seed. "@ capacity" rows use the label-free threshold that sends the most alerts without breaching the ceiling.

## dev (seed 42, thresholds calibrated here)

Window 2026-06-29 → 2026-09-27 (13 weeks), 5 AEs, capacity 50/week. Thresholds (dev F1 / capacity): engine 18.43 / 2.40, static points 45.18 / 17.00. Positives: 25.

| Method | Alerts | Alerts/AE/week | Busiest week | Precision (alerts) | Precision (accounts) | Recall | Median lead (days) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Per-event pings | 1,036 | 15.9 | 96 | 23.6% | 7.9% | 88.0% (22/25) | 21 |
| Static points @ capacity | 186 | 2.9 | 22 | 8.6% | 8.6% | 64.0% (16/25) | 18 |
| Static points @ dev F1 | 76 | 1.2 | 10 | 19.7% | 19.7% | 60.0% (15/25) | 13 |
| Engine M1 @ capacity | 557 | 8.6 | 50 | 1.6% | 2.6% | 36.0% (9/25) | 30 |
| Engine M1 | 42 | 0.6 | 5 | 42.9% | 48.6% | 68.0% (17/25) | 14 |

Hand-raises routed outside scoring (demo requests): 16. Post-meeting alerts dropped from metrics: Per-event pings 4, Static points @ capacity 0, Static points @ dev F1 1, Engine M1 @ capacity 0, Engine M1 0.

**Hard-negative accounts alerted** (distinct accounts, of those planted per type)

| Type | Planted | Per-event pings | Static points @ capacity | Static points @ dev F1 | Engine M1 @ capacity | Engine M1 |
|---|---:|---:|---:|---:|---:|---:|
| bot_burst | 8 | 3 | 3 | 0 | 4 | 0 |
| content_binger | 8 | 3 | 6 | 6 | 8 | 5 |
| customer_active | 8 | 0 | 0 | 0 | 0 | 0 |
| low_fit_active | 8 | 0 | 0 | 0 | 0 | 0 |
| open_deal_active | 8 | 0 | 0 | 0 | 0 | 0 |
| pricing_hammerer | 8 | 8 | 7 | 7 | 7 | 7 |
| stalled_trial | 8 | 8 | 2 | 1 | 7 | 0 |
| trigger_only | 8 | 0 | 7 | 0 | 6 | 0 |

**Positives the engine missed:** 8

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

Window 2026-06-29 → 2026-09-27 (13 weeks), 5 AEs, capacity 50/week. Thresholds (dev F1 / capacity): engine 18.43 / 2.40, static points 45.18 / 17.00. Positives: 25.

| Method | Alerts | Alerts/AE/week | Busiest week | Precision (alerts) | Precision (accounts) | Recall | Median lead (days) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Per-event pings | 1,110 | 17.1 | 115 | 21.9% | 7.6% | 96.0% (24/25) | 20 |
| Static points @ capacity | 179 | 2.8 | 21 | 9.5% | 9.5% | 68.0% (17/25) | 14 |
| Static points @ dev F1 | 81 | 1.2 | 11 | 19.8% | 19.8% | 64.0% (16/25) | 12 |
| Engine M1 @ capacity | 571 | 8.8 | 55 | 3.7% | 4.7% | 68.0% (17/25) | 26 |
| Engine M1 | 42 | 0.6 | 7 | 42.9% | 51.5% | 68.0% (17/25) | 10 |

Hand-raises routed outside scoring (demo requests): 29. Post-meeting alerts dropped from metrics: Per-event pings 12, Static points @ capacity 0, Static points @ dev F1 3, Engine M1 @ capacity 6, Engine M1 0.

**Hard-negative accounts alerted** (distinct accounts, of those planted per type)

| Type | Planted | Per-event pings | Static points @ capacity | Static points @ dev F1 | Engine M1 @ capacity | Engine M1 |
|---|---:|---:|---:|---:|---:|---:|
| bot_burst | 8 | 2 | 2 | 0 | 2 | 0 |
| content_binger | 8 | 2 | 6 | 8 | 8 | 3 |
| customer_active | 8 | 0 | 0 | 0 | 0 | 0 |
| low_fit_active | 8 | 0 | 0 | 0 | 0 | 0 |
| open_deal_active | 8 | 0 | 0 | 0 | 0 | 0 |
| pricing_hammerer | 8 | 8 | 6 | 7 | 7 | 7 |
| stalled_trial | 8 | 8 | 0 | 1 | 6 | 0 |
| trigger_only | 8 | 0 | 6 | 0 | 6 | 1 |

**Positives the engine missed:** 8

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
