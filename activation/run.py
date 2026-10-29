"""Daily activation: today's alerts → explanations → Slack digest (or a dry-run file).

Reads the warehouse read-only and never touches the truth labels: the digest shows only what a real team would know.
Writes its narrative cache and post log to the app state file (app/state.py), never to the warehouse.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import duckdb

from activation import narrate, slack
from app import state

CHANNEL = "webhook"
MAX_NARRATED = 20  # explanations per day; the per-AE budget keeps real volumes well below this


def replay_date(params: dict[str, str], today: date) -> date:
    """Synthetic data is fixed, so each daily run replays one day of the evaluation window, in order, then loops."""
    start, end = date.fromisoformat(params["eval_start"]), date.fromisoformat(params["eval_end"])
    span = (end - start).days + 1
    offset = (today - date.fromisoformat(params["replay_launch_date"])).days % span
    return start + timedelta(days=offset)


def _rows(con: duckdb.DuckDBPyConnection, sql: str, args: list) -> list[dict]:
    cur = con.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def collect(db: str | Path, as_of: date | None, today: date) -> dict:
    con = duckdb.connect(str(db), read_only=True)
    try:
        params = dict(con.execute("select param, value from seeds.scoring_params").fetchall())
        as_of = as_of or replay_date(params, today)
        profile = params["active_profile"]
        alerts = _rows(con, """
            select a.account_id, a.alert_date, a.owner_ae_id, a.engine_score as score, a.alert_kind, c.*
            from gold.engine_alerts a
            join gold.alert_context c using (account_id, alert_date)
            where a.is_active and a.alert_date = ?
            order by a.engine_score desc
        """, [as_of])
        handraises = _rows(con, """
            select distinct h.account_id, s.company_name, h.owner_ae_id
            from gold.handraise_routes h join staging.stg_accounts s using (account_id)
            where h.routed_date = ? order by 2
        """, [as_of])
        week_start = as_of - timedelta(days=as_of.weekday())
        alerts_this_week = con.execute("select count(*) from gold.engine_alerts where is_active and alert_date between ? and ?",
                                       [week_start, as_of]).fetchone()[0]
        today_decisions = dict(con.execute("""select status, count(*) from gold.alert_candidates
                                               where profile = ? and score_date = ? group by 1""", [profile, as_of]).fetchall())
    finally:
        con.close()
    week = {
        "alerts_this_week": alerts_this_week,
        "capacity": int(params["capacity_per_week"]),
        "held_by_cooldown": today_decisions.get("cooldown", 0),
        "deferred": today_decisions.get("deferred", 0),
    }
    return {"as_of": as_of, "profile": profile, "alerts": alerts, "handraises": handraises, "week": week}


def explain(alerts: list[dict], cfg: narrate.LLMConfig | None, caller: Callable = narrate.call_llm) -> dict[str, int]:
    """Attach a narrative to each alert (cache first). Returns counts by source."""
    counts = {"llm": 0, "template": 0, "cached": 0}
    for i, a in enumerate(alerts):
        facts = narrate.facts_from_context(a)
        a["people"] = facts["people"]
        h = narrate.facts_hash(facts)
        hit = state.cached_narrative(a["account_id"], a["alert_date"], h)
        if hit and (hit["source"] == "llm" or cfg is None):
            a["narrative"], counts["cached"] = hit["content"], counts["cached"] + 1
            continue
        n = narrate.narrate(facts, cfg if i < MAX_NARRATED else None, caller)
        state.save_narrative(a["account_id"], a["alert_date"], h, n.source, n.model, n.content, n.problems)
        # One line per alert in the run log (CI keeps no state, so this is how a fallback gets diagnosed).
        print(f"explain {a['account_id']}: {n.source}" + (f" ({'; '.join(n.problems)[:300]})" if n.problems else ""))
        a["narrative"] = n.content
        counts[n.source] += 1
    return counts


def run(db: str | Path, as_of: date | None = None, dry_run: bool = False, out_dir: Path = Path("out"), force: bool = False,
        today: date | None = None, caller: Callable = narrate.call_llm, poster: Callable = slack.post) -> dict:
    data = collect(db, as_of, today or date.today())
    counts = explain(data["alerts"], narrate.LLMConfig.from_env(), caller)
    payload = slack.build_digest(data["as_of"], data["profile"], data["alerts"], data["handraises"], data["week"],
                                 os.environ.get("APP_BASE_URL"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"digest_{data['as_of']}.json"
    out_file.write_text(json.dumps(payload, indent=2, default=str))

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    channel = CHANNEL + ":" + hashlib.sha256((webhook or "").encode()).hexdigest()[:8]
    if dry_run or not webhook:
        status = "dry_run"
    elif state.already_posted(data["as_of"], data["profile"], channel) and not force:
        status = "skipped_already_posted"
    else:
        poster(webhook, payload)
        status = "posted"
    state.log_activation(data["as_of"], data["profile"], channel, status, len(data["alerts"]), json.dumps(counts))
    return {"as_of": data["as_of"], "profile": data["profile"], "alerts": len(data["alerts"]),
            "handraises": len(data["handraises"]), "narratives": counts, "status": status, "file": str(out_file)}
