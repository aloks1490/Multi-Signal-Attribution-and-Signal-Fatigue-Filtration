# Signal Engine

Account-level intent scoring that replaces one-alert-per-event with a short list of accounts showing a buying pattern. It is evaluated on a synthetic market where the real buyers are known to the evaluator but hidden from the scoring code.

- Design rationale: [context.md](context.md)
- Build spec (stack, schema, scoring, tests): [docs/implementation.md](docs/implementation.md)
- Latest numbers: [docs/results.md](docs/results.md)

## Results (holdout seed)

| Method | Alerts in 13 weeks | Alerts/AE/week | Alerted accounts that were buyers | Buyers caught |
|---|---:|---:|---:|---:|
| Ping on every pricing/security/demo event | 1,149 | 17.7 | 7.6% | 96% |
| Static lead points (no decay), recall-weighted | 92 | 1.4 | 20.7% | 76% |
| Engine M1 (decay + fit gate + exclusions) | 27 | 0.4 | 55.6% | 60% |
| Engine M2, precise profile (F1) | 16 | 0.2 | 86.7% | 52% |
| **Engine M2, broad profile (F2, active)** | **44** | **0.7** | **48.6%** | **68%** |

The engine keeps two thresholds, both tuned on dev data: **precise** (fewer, surer alerts) and **broad** (catches more buyers). A team-level `active_profile` setting picks which one reaches reps. At the same alert budget M2 beats M1 and static points on both precision and recall (≈40 alerts: 55% / 68% vs 49% / 64% and 15% / 24%). Details: [docs/results.md](docs/results.md). Synthetic data proves the machinery, not the weights.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
make setup     # install dependencies
make m1        # dev world → dbt → calibrate → holdout world → docs/results.md (~50 s)
make test      # pytest: generator, metrics, calibration, truth wall, point-in-time
```

Individual steps:

```bash
make generate NAME=dev SEED=42          # synthetic world → data/dev.duckdb
make build NAME=dev                      # dbt seeds, models, data tests, unit tests
make calibrate                           # thresholds from the dev seed → seeds/scoring_params.csv
make report                              # docs/results.md
```

## Layout

```
generator/     synthetic world (the only code that knows the truth)
dbt_project/   staging → silver → gold models, seeds = tuning config
eval/          calibration, metrics, results report (reads truth labels)
tests/         pytest suite
docs/          implementation spec and results
```
