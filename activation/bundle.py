"""Explain every holdout alert once and save the results to a file the app ships with.

python -m activation.bundle --db data/holdout.duckdb --out app/narratives_holdout.json

The hosted app has no LLM key and no daily-run state, so without this its alert feed would show only the rule-based
reason. Same client, prompt and fact checker as the daily run; an alert the model fails on keeps the template, as it
would in Slack. Run it from the "Bundle explanations" workflow (uses the repository's LLM secret) and commit the file.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from activation import narrate
from activation.run import _rows

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "app" / "narratives_holdout.json"


def alerts(db: str | Path) -> list[dict]:
    """Every distinct (account, alert date) in the evaluation window, for both profiles."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        start = con.execute("select value from seeds.scoring_params where param = 'eval_start'").fetchone()[0]
        return _rows(con, """
            select c.* from (select distinct account_id, alert_date from gold.engine_alerts
                             where alert_date >= cast(? as date)) a
            join gold.alert_context c using (account_id, alert_date)
            order by alert_date, account_id
        """, [start])
    finally:
        con.close()


def build(rows: list[dict], cfg: narrate.LLMConfig | None, pause: float = 2.0, retry_wait: float = 15.0,
          caller=narrate.call_llm, log=print) -> dict:
    items, sources = [], Counter()
    for i, row in enumerate(rows):
        facts = narrate.facts_from_context(row)
        n = narrate.narrate(facts, cfg, caller)
        if cfg is not None and n.source == "template" and any(p.startswith("llm error") for p in n.problems):
            time.sleep(retry_wait)  # free tiers rate-limit; one retry before settling for the template
            n = narrate.narrate(facts, cfg, caller)
        sources[n.source] += 1
        log(f"{i + 1:>3}/{len(rows)} {row['account_id']} {row['alert_date']} {n.source}"
            + (f"  ({'; '.join(n.problems)[:200]})" if n.problems else ""))
        items.append({"account_id": row["account_id"], "alert_date": str(row["alert_date"]),
                      "facts_hash": narrate.facts_hash(facts), "source": n.source, "model": n.model,
                      "narrative": n.content, "problems": n.problems})
        if cfg is not None and pause:
            time.sleep(pause)
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": cfg.model if cfg else None, "world": "holdout (seed 7)",
            "counts": dict(sources), "narratives": items}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/holdout.duckdb")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between calls (free tiers limit requests per minute)")
    args = ap.parse_args()
    cfg = narrate.LLMConfig.from_env()
    if cfg is None:
        raise SystemExit("Set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL) to bundle explanations.")
    bundle = build(alerts(args.db), cfg, args.pause)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n")
    c = bundle["counts"]
    print(f"\nmodel={bundle['model']} written by the model: {c.get('llm', 0)}/{sum(c.values())} → {args.out}")


if __name__ == "__main__":
    main()
