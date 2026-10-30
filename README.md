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
| Engine M1 (decay + fit gate + exclusions) | 43 | 0.7 | 55.6% | 60% |
| Engine M2, precise profile (F1) | 26 | 0.4 | 86.7% | 52% |
| **Engine M2, broad profile (F2, active)** | **67** | **1.0** | **48.6%** | **68%** |

The engine keeps two thresholds, both tuned on dev data: **precise** (fewer, surer alerts) and **broad** (catches more buyers); a team-level `active_profile` picks which one reaches reps. Alerts pass through a 14-day cooldown (broken by a 1.5× score jump) and a per-AE budget of 2 a day and 10 a week. At the same alert budget M2 beats M1 and static points on both precision and recall. Details: [docs/results.md](docs/results.md). Synthetic data proves the machinery, not the weights.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
make setup     # install dependencies
make m1        # dev world → dbt → calibrate → holdout world → docs/results.md (~50 s)
make test      # pytest: generator, metrics, calibration, truth wall, point-in-time, app
make app       # Streamlit app on http://localhost:8501
uv run python -m activation --as-of 2026-08-03 --dry-run   # build one day's Slack digest into out/
```

**HubSpot (M5).** The daily run reads exclusions back from HubSpot before scoring (a rep marking a company as a customer stops its alerts) and afterwards pushes score, tier, reason and the model's headline to company records, the buying group as contacts, and one task per alert. Without a `HUBSPOT_TOKEN` it is a dry run. Setup: [docs/implementation.md §15](docs/implementation.md).

**Daily digest (M4).** `.github/workflows/daily.yml` rebuilds the world at 06:00 UTC on weekdays, applies cooldown and a per-AE budget, has an LLM (any OpenAI-compatible free tier: OpenRouter or NVIDIA NIM) explain each alert from a fact sheet, rejects anything not in the facts, and posts one Slack message. Without secrets it runs as a dry run. Setup: [docs/implementation.md §14](docs/implementation.md).

The app has five pages: **Overview** (pings vs static points vs engine, precise/broad trade-off), **Alert feed** (reasons, accept/dismiss), **Account deep-dive** (score history, step-by-step breakdown, decay, who did what), **Tuning sandbox** (edit weights, rebuild on a copy of dev, compare) and **Settings** (which profile reps receive, with an audit log).

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
app/           Streamlit app; queries.py and charts.py are UI-free for the later Reflex port
engine/        alerting rules (cooldown, score jump, per-AE budget)
activation/    explanations, Slack digest, HubSpot sync, daily run
tests/         pytest suite
docs/          implementation spec and results
```
