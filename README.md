# Signal Engine

Account-level intent scoring that replaces one-alert-per-event with a short list of accounts showing a buying pattern. It is evaluated on a synthetic market where the real buyers are known to the evaluator but hidden from the scoring code.

- Design rationale: [context.md](context.md)
- Build spec (stack, schema, scoring, tests): [docs/implementation.md](docs/implementation.md)
- Latest numbers: [docs/results.md](docs/results.md)

## M1 result (holdout seed)

| Method | Alerts in 13 weeks | Alerts/AE/week | Alerted accounts that were buyers | Buyers caught |
|---|---:|---:|---:|---:|
| Ping on every pricing/security/demo event | 1,110 | 17.1 | 7.6% | 96% |
| Static lead points (no decay) | 81 | 1.2 | 19.8% | 64% |
| **Engine M1** (decay + fit gate + exclusions) | **42** | **0.6** | **51.5%** | **68%** |

Synthetic data proves the machinery, not the weights. Pattern rules (breadth, spike, combos) come in M2.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
make setup     # install dependencies
make m1        # dev world → dbt → calibrate → holdout world → docs/results.md (~40 s)
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
