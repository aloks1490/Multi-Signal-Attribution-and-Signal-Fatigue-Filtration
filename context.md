# Context: GTM Signal Engine (signal-fatigue scoring project)

Handoff from a previous chat. Read this first; it captures what was decided and why.

## About me

- Alok Singh, final-year E&TC engineering student (Pune, India), pivoting into a **GTM Engineer** role at early-stage B2B SaaS startups.
- Doing the Clay Alphaforge GTM Engineering bootcamp. This project is being discussed with people from that course (mix of marketing/demand-gen and technical backgrounds).
- Background that matters for this project: Python, SQL, Databricks (built a Medallion ETL on NYC Taxi data), dbt + DuckDB (Olist lakehouse), GCP streaming pipeline (Pub/Sub, Beam, BigQuery), a fraud-detection project (6.3M rows), plus Clay / n8n / HubSpot.
- Related portfolio project: a Slack `@lead-research` bot (n8n + Clay + Supabase + HubSpot) for prospect enrichment and outreach suppression. The signal engine could call it for accounts that cross the threshold.

## The problem being solved

From a source PDF ("VITAL problems that GTM Engineering solve"), enterprise problem #2: **signal fatigue / alert blindness**.

- Companies log huge volumes of events (web visits, product usage, ads, email, job changes, intent data).
- Naive setups fire an alert per "interesting" event, reps get dozens a day, ignore all of them, and miss real buyers.
- Core insight: **a single event carries almost no information; patterns do.**
- Real intent = breadth (several people from one account), channel mix, acceleration vs the account's own baseline, and at least one high-intent signal (security, pricing, integration docs).

Note: the source PDF reads as AI-generated (fake citations). Treat it as a map of the field, not a reliable source. Its claim that this needs Kafka/real-time is mostly wrong; see "Batch vs real-time".

## Design (what was agreed)

### 1. Fit vs timing (two axes, not one sum)
- **Fit (ICP):** firmographics + current tech stack. Slow-changing, **no decay**.
- **Timing:** triggers + engagement. **Decays.**
- 2x2: high fit + high intent = outreach now; high fit + low intent = keep warm; low fit + high intent = likely noise; low fit + low intent = ignore.
- Fit acts as a gate or multiplier on the timing score, so a busy bad-fit account can't outscore a great-fit account that just raised money.

### 2. Signal catalog (half-lives are starting assumptions to tune)
| Signal | Type | Half-life |
|---|---|---|
| Company size, industry, region | Fit | none |
| Current tech stack | Fit | none |
| Funding round | Trigger | 60–90 days |
| New exec hire (VP Sales, Head of RevOps) | Trigger | ~90 days |
| Job posts for relevant roles | Trigger | while posts are open |
| Tool adopted or dropped | Trigger | 30–60 days |
| Web / product / email activity | Engagement | days |

- Combinations matter: funding alone is weak; funding + SDR job posts + new VP Sales within 60 days is strong.
- **Signal crowding:** popular public signals (funding) lose value because everyone acts on them. Edge comes from combinations and less-watched signals.

### 3. Scoring model
- Engagement weights (assumptions): security page 8 (7d), pricing 5 (5d), new VP 4 (60d), API docs 3 (10d), trial started 3 (14d), ad click 1 (3d), blog 0.5 (3d).
- Time decay: `base = Σ w_i · 2^(−a_i / h_i)` (a = event age in days, h = half-life).
- Pattern multipliers: breadth (e.g. 1 person ×1.0, 2 ×1.3, 3+ ×1.6), channel mix, named combination bonuses (e.g. docs + security page within 14 days), acceleration (last 7 days vs own 8-week average).
- `score = base × m_breadth × m_channels × m_spike + combo bonuses`
- All weights/multipliers live in a dbt seed file so tuning is config, not code.

### 4. Filtering and suppression
1. Threshold (or top N per rep), with tiers Hot / Warm / Watch.
2. Cooldown after an alert unless the score jumps sharply.
3. Exclusions from HubSpot: open deal, existing customer, competitor, do-not-contact.
4. Every alert carries a one-line reason, e.g. "Acme: 82 · 3 people · security + API docs + pricing · 4× normal activity".

### 5. Outreach response as a signal (my idea)
- Reactions to outreach are the strongest intent signal and get scored: positive reply / meeting (very strong, route to AE), referral (strong, add contact), return pricing visit via tracked link (strong), new person from the account visits after outreach (strong), "not now" (pause + re-engage date), link click (weak), email open (~zero, inflated by mail privacy features), no reply (mild negative), unsubscribe / not interested (suppress), bounce / left company (data update; replacement hire can be a trigger).
- Requires tracked links + IDs on every touch.
- **Two separate models:** pre-outreach (who to contact) and post-outreach (who to push / pause). Responses must NOT be used as inputs when backtesting pre-outreach signals (leakage).
- Person-level visitor identification by IP is vendor- and law-dependent (restricted under GDPR in the EU); tracked-link clicks and logins are reliable.

### 6. Buying group (my idea)
- If 3 people at different seniority visit pricing, contact all 3 with one story framed per role (exec: outcome/cost; manager: process/efficiency; IC: how it works/integrations). Stagger sends, cap touches per account per week.
- Track two rates per persona: P(reply) and P(deal advances | persona engaged). The one who replies most is often not the one who closes.
- Prioritize by `EV = P(reply) × P(advance | engaged)`.
- Tag roles over time: champion, economic buyer, user/influencer, blocker. Single-threaded deals are fragile.
- Needs many accounts for persona conclusions; in the synthetic build, plant known response rates per persona and show the analysis recovers them.

### 7. Batch vs real-time
- Daily/hourly batch in the warehouse is enough; B2B intent builds over days/weeks.
- Optional fast path only for hand-raises (demo request, trial sign-up from a target account).
- State this trade-off explicitly in the README; it shows judgment.

### 8. Evaluation
- Metrics: alerts per rep per week (down), precision (alerts → meeting/opp, up), recall (real buyers caught, high).
- Synthetic test: ~500 accounts, ~100k events, mostly noise, ~10 **planted buyers** following the intent pattern. Compare naive rule vs engine on alert count and planted buyers caught.

### 9. Backtesting
1. Clear outcome labels (meeting / opp / closed-won).
2. Point-in-time data only (no signals after the outcome date): the most common mistake.
3. Per-signal lift = signal's conversion rate / base rate (~3× earns its weight, ~1× is noise). Logistic regression can learn weights with enough outcomes.
4. Selection bias: outcomes only exist for contacted accounts, so contact a small random sample regardless of score.
- Set the threshold from rep capacity (e.g. 50 accounts/week → the score that yields ~50), then check precision.
- The backtest also tests the ICP: if low-fit accounts convert, the ICP is wrong.
- On synthetic data, a backtest proves the machinery, not real-world weights. Say so in the README.

## Architecture and stack

Pipeline: event sources → bronze (raw events) → silver (events mapped to accounts by email domain / IP-to-company, plus weights) → **gold: scoring in dbt** (decay + multipliers) → filter (threshold, cooldown, exclusions) → activate (HubSpot score / tier / reason, Slack digest) → feedback (replies, meetings, opps, precision) → tune weights.

| Layer | Tool |
|---|---|
| Data generation | Python + Faker |
| Storage / processing | Databricks bronze / silver / gold (DuckDB is the easier group option) |
| Modelling | dbt |
| Activation | HubSpot sandbox via reverse ETL |
| Orchestration | GitHub Actions (daily) |
| Reporting | Slack |

## Build plan (milestones, each shippable alone)

1. **Data + base score (start here).** Faker script (~500 accounts, ~100k noisy events, ~10 planted buyers), bronze/silver tables, one dbt model computing decayed scores per account. Output: naive alert count vs engine alert count, and planted buyers caught. Leaves out multipliers, suppression, HubSpot, Slack. Fits in one or two weekends and gives a first demo + LinkedIn post. Every later milestone is measured against this baseline.
2. **Pattern rules:** breadth, channel mix, two combination rules, baseline spike. Output: planted-buyer recall.
3. **Suppression + reasons:** threshold, cooldown, exclusions, one-line alert explanation.
4. **Activation:** HubSpot push, daily GitHub Actions, Slack summary.
5. **Write-up:** README with architecture, trade-offs (incl. batch over streaming), results table.

## Group collaboration plan (proposed before a meeting with course peers)

Recommended: **one shared repo with a shared core and per-person scoring variants**, not separate forks.

```
signal-engine/
  shared/
    generator/   # one Faker script, fixed random seed
    schema/      # event + account tables
    signals.csv  # agreed signal list
    eval/        # one script: alerts sent, planted buyers caught, precision
  variants/
    <name>/      # each person's dbt models + weights
  results.md     # leaderboard, one row per variant
```

- Same data + same planted buyers = comparable results. People edit only their own folder; `shared/` changes go through reviewed PRs.
- Non-coders can own a variant via a weights/rules CSV that a technical teammate runs.
- Decisions to lock: fictional product + ICP, signal list, success metric (e.g. best recall within 50 alerts), stack (Databricks vs local dbt + DuckDB), owners for generator + eval, due date.
- Settle repo ownership and credit up front (e.g. repo under my GitHub, everyone a collaborator and named in the README).
- Questions planned for marketing/demand-gen peers: which signals actually predicted deals, why reps ignored alerts, what an actionable alert needs, real buying-committee shape at the ICP, buying-window length (sets half-lives), touch caps, typical reply rates by persona.
- **Outcome of that meeting is not recorded here.** Fill in what was decided.

## Artifacts already made

- Claude Doc "Signal Fatigue in Enterprise GTM: Problem and Solution Design": https://claude.ai/artifact/8YcE8o9bbAH2T42ya9yCuG (full design, with fit-vs-timing 2x2 and pipeline diagrams).
- PDF export of that doc for sharing: `Signal_Fatigue_in_Enterprise_GTM.pdf` (8 pages, A4, formulas and diagrams rendered properly).

## Sales/marketing input (flow.jpeg, 26 Oct 2026)

A sales and marketing contact sketched the flow in `flow.jpeg`:
- Qualification uses three scores: **lead score** (static fit: size, revenue, tech stack, location), **activity score** (website + product usage, PQL actions such as inviting teammates), **signals** (funding, new hire, press release, product launch). Hot accounts are routed to sales via Slack.
- Clay (or Deepline) supplies trigger signals and writes them to HubSpot; product usage comes from Mixpanel or similar; all data goes to Snowflake/dbt, where **decay happens and nowhere else**; Claude sits between the warehouse and Slack as an intelligence layer; outreach status syncs back to HubSpot.
- Every activity needs a weight, a half-life and a funnel stage (TOFU / MOFU / BOFU).

What we adopted and changed:
- Raw events go **straight to the warehouse**, not through HubSpot (free tier has no custom behavioural events; API rate limits). HubSpot is the system of record for people, companies, deals and exclusions, and receives scores back.
- **Claude does not produce the score.** Decay scoring ranks every account (cheap, reproducible, backtestable). Claude classifies unstructured signals (press releases, job-post wording) into taxonomy types and writes the alert text for the top N accounts from structured facts. "Which signals matter" is answered by the backtest (lift), not by the LLM.
- Email opens weigh 0 (Apple Mail Privacy Protection inflates them).
- Teammate invites are a strong breadth signal from product data.

## Comparable project reviewed (27 Oct 2026)

`github.com/backend-bytes127/gtm-signal-engine` (Neeraj Sujan, last commit 25 Oct 2026): DuckDB + dbt + Dagster + Next.js + HubSpot/Attio/Slack, built almost verbatim from this design doc. Polished and end to end, but: tiers are daily percentiles (top 30% is always "hot"), the 5-alert budget is global rather than per AE, triggers appear only in planted buyers (circular), noise is uniform rather than heavy-tailed, no hard negatives, cooldown and do-not-contact are not implemented, fit is a hard filter, scores use `current_date` (no point-in-time, no backtest), and there is no naive-vs-engine or precision number. Our edge is the evaluation: realistic noise and hard negatives, absolute scores with a capacity threshold, point-in-time scoring, dev/holdout seeds, and a per-event vs static-points vs engine results table. Whether Neeraj is in the course group is still unknown; check before publishing.

## Decisions locked (27 Oct 2026)

Full spec: [docs/implementation.md](docs/implementation.md).

- **Product:** Seqly (fictional), a sales-engagement platform. ICP: B2B software/fintech/martech/HR tech/cybersecurity/data, 50–1,000 employees, NA/EU, Salesforce or HubSpot CRM, sales headcount ≥ 5.
- **Stack:** Python 3.12 via uv, Faker, DuckDB, dbt-core + dbt-duckdb, Streamlit (M3; Reflex migration later, data access kept framework-agnostic), HubSpot free, Slack webhook, Claude Haiku, GitHub Actions. No Snowflake (trial expires), no Databricks (optional port later).
- **Baselines:** per-event pings and static (no-decay) points; the engine must beat both.
- **Capacity:** 5 AEs × 10 alerts/week = 50/week; threshold calibrated from capacity on the dev seed.
- **Scale:** 2,000 accounts (standard profile), so 50/week is a real filter; 200-account small profile for tests.
- **Seeds:** 42 = dev, 7 = holdout (reported).
- **Repo:** solo project; group variants can be added later.
- **Threshold rule (changed during M1):** capacity is a hard ceiling, not a target. Filling 50/week dropped the threshold to one pricing visit and wrecked precision. Deployed thresholds are tuned for F1 on the dev seed under the ceiling, then applied unchanged to holdout.
- Status (27 Oct 2026): **M1 built and passing** (71 dbt nodes incl. 8 unit tests, 24 pytest tests). Holdout: engine 42 alerts / 51.5% account precision / 68% recall vs per-event pings 1,110 / 7.6% / 96% and static points 81 / 19.8% / 64%. Remaining M1 failures for M2: pricing hammerers (7/8 alerted) and content bingers (3/8). Nothing committed to git yet.

## M2 (29 Oct 2026)

- Built: breadth, sources, spike (only with ≥ 2 people), high-intent gate (×0.6 without BOFU), four combos (trigger combos need engagement), rolling-hour bot window, time-aware people counts, one-line reasons.
- Holdout at deployed (dev-F1) thresholds: M2 16 alerts / 86.7% precision / 52% recall vs M1 27 / 55.6% / 60%. At equal alert budgets M2 beats M1 on both (≈40 alerts: 55% / 68% vs 49% / 64%). Hammerer alerts 7 → 2, binger 2 → 0.
- Weak spot: 2-person "quiet" buyers (4 of 12 misses).
- **Decided: keep both thresholds.** precise = best dev F1, broad = best dev F2; dbt writes alerts for both (`profile` column). `active_profile` in scoring_params (default `broad`) decides what reps receive. The frontend (M3) gets an explore toggle (viewer only) and a separate, confirmed and logged active setting. F2 was added after the first holdout read; stated in the docs.
- Holdout, broad (active): 44 alerts / 48.6% precision / 68% recall (17 of 20 planted buyers). Precise: 16 / 86.7% / 52%.

## M3 (29 Oct 2026)

- Streamlit app (`make app`): Overview, Alert feed, Account deep-dive, Tuning sandbox, Settings. Explore toggle in the sidebar (viewer only); the active profile is changed only in Settings (reason + confirmation, rebuilds `engine_alerts`, audit log in `data/app_state.duckdb`).
- Built for the Reflex port: `app/queries.py`, `app/charts.py`, `app/state.py`, `app/sandbox.py` have no Streamlit imports; Reflex state handlers can call them unchanged.
- DuckDB rule that shaped the design: one writer or many readers, so the app opens the warehouse read-only per call and keeps its own state in a separate file.

## M4 (29 Oct 2026)

- Decided: cooldown 14 days, score-jump override ×1.5 after ≥ 3 days, per-AE budget 2/day and 10/week, deferral up to 3 days then drop; one Slack channel digest via webhook; replay clock for the daily run; **open-source LLM on a free tier (OpenRouter or NVIDIA NIM) instead of Claude**, through one OpenAI-compatible client (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`).
- Built: `engine/alerting.py` (shared by the dbt Python model `alert_candidates` and by calibration), `gold.alert_context` fact sheets, `activation/` (checker rejects invented people, numbers and names; template fallback; cache; post-once log), `.github/workflows/ci.yml` and `daily.yml`. The repo is now an installable package (hatchling) so dbt's Python model can import `engine`.
- Holdout after M4: broad 67 alerts (jump re-alerts added), 55% alert precision, 48.6% account precision, 68% recall; budget never binds at this volume.
- To go live: add `SLACK_WEBHOOK_URL`, `LLM_API_KEY` secrets and `LLM_BASE_URL`, `LLM_MODEL` variables in GitHub.
- Live since 29 Oct 2026: NVIDIA NIM, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, `LLM_EXTRA_BODY` turns its reasoning off (otherwise it spent the whole token budget thinking and returned no answer). First live post (28 Jul replay) went out with template explanations; after the fix, 3/3 explanations come from the model and pass the checker.
