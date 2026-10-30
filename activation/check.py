"""LLM acceptance check: explain a sample of alerts across the window and report how many pass the fact checker.

python -m activation.check --db data/holdout.duckdb --n 40
Uses the same client, prompt and checker as the daily run, but writes nothing (no cache, no Slack).
"""
from __future__ import annotations

import argparse
import re
import time
from collections import Counter

import duckdb

from activation import narrate
from activation.run import _rows


def sample(db: str, n: int) -> list[dict]:
    con = duckdb.connect(db, read_only=True)
    try:
        start = con.execute("select value from seeds.scoring_params where param = 'eval_start'").fetchone()[0]
        return _rows(con, """
            select c.* from gold.engine_alerts a join gold.alert_context c using (account_id, alert_date)
            where a.is_active and a.alert_date >= cast(? as date)
            order by hash(a.account_id || cast(a.alert_date as varchar)) limit ?
        """, [start, n])
    finally:
        con.close()


def category(problem: str) -> str:
    return re.split(r"[:(]", problem, maxsplit=1)[0].strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/holdout.duckdb")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between calls (free tiers limit requests per minute)")
    args = ap.parse_args()
    cfg = narrate.LLMConfig.from_env()
    if cfg is None:
        raise SystemExit("Set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL) to run the check.")
    alerts = sample(args.db, args.n)
    sources, problems = Counter(), Counter()
    for i, a in enumerate(alerts):
        n = narrate.narrate(narrate.facts_from_context(a), cfg)
        sources[n.source] += 1
        for p in n.problems:
            problems[category(p)] += 1
        print(f"{i + 1:>3}/{len(alerts)} {a['account_id']} {n.source}" + (f"  ({'; '.join(n.problems)[:160]})" if n.problems else ""))
        time.sleep(args.pause)
    total = sum(sources.values())
    print(f"\nmodel={cfg.model} accepted={sources['llm']}/{total} ({sources['llm'] / max(total, 1):.0%})")
    for k, v in problems.most_common():
        print(f"  rejected or failed for '{k}': {v}")


if __name__ == "__main__":
    main()
