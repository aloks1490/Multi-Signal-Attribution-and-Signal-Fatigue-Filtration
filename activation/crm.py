"""HubSpot sync (M5).

pull: HubSpot → bronze.hubspot_companies (lifecycle stage, open deals, do-not-contact). Runs before dbt, so a rep's
      change in the CRM becomes an exclusion on the next run.
push: warehouse → HubSpot, after the Slack digest:
      - companies that reached Watch or alerted (up to the run day): score, tier, reason, headline, last alert
      - contacts: the active buying group of today's alerts, linked to their company
      - one task per new alert (searched by subject first, so re-runs never duplicate)
      Rep-owned fields (lifecycle stage, do-not-contact) are never written by the push.

Without HUBSPOT_TOKEN both steps are dry runs: push writes the planned payloads to out/hubspot_<date>.json.
Like the digest, the sync never reads the truth labels.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from activation.hubspot import HubSpot
from activation.run import _rows, replay_date
from app import state

GROUP = "signal_engine"
# Synthetic companies can share domains with real ones (e.g. cox.com). HubSpot enriches companies by domain and links
# contacts by email domain, so every pushed domain and email gets the reserved .example suffix (RFC 2606): it can never
# collide with a real company, and contacts still match their company.
SYNTHETIC_SUFFIX = ".example"
TIERS = ["Hot", "Warm", "Watch", "Below", "Excluded"]
OPEN_DEAL_CANDIDATES = ("hs_num_open_deals", "num_associated_deals")  # HubSpot does not publish the internal name; use the first that exists


def company_properties() -> list[dict]:
    """Nine custom company properties (the free plan allows ten)."""
    def prop(name, label, type_, field, **extra):
        return {"name": name, "label": label, "type": type_, "fieldType": field, "groupName": GROUP, **extra}
    return [
        prop("signal_account_id", "Signal account id", "string", "text", hasUniqueValue=True),
        prop("signal_score", "Signal score", "number", "number"),
        prop("signal_tier", "Signal tier", "enumeration", "select",
             options=[{"label": t, "value": t, "displayOrder": i} for i, t in enumerate(TIERS)]),
        prop("signal_fit_grade", "Signal fit grade", "string", "text"),
        prop("signal_reason", "Signal reason", "string", "textarea"),
        prop("signal_headline", "Signal headline", "string", "textarea"),
        prop("signal_last_alert_date", "Signal last alert", "date", "date"),
        prop("signal_owner_ae", "Signal owner AE", "string", "text"),
        prop("signal_do_not_contact", "Do not contact (Signal Engine)", "bool", "booleancheckbox",
             options=[{"label": "Yes", "value": "true", "displayOrder": 0}, {"label": "No", "value": "false", "displayOrder": 1}]),
    ]


def client_from_env() -> HubSpot | None:
    token = os.environ.get("HUBSPOT_TOKEN")
    return HubSpot(token) if token else None


def _midnight_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


# ---------- pull ----------

def pull(db: str | Path, hs: HubSpot | None) -> dict:
    """Replace bronze.hubspot_companies with HubSpot's current state for synced companies."""
    if hs is None:
        return {"status": "not_connected", "companies": 0}
    names = hs.property_names("companies")
    deals_prop = next((p for p in OPEN_DEAL_CANDIDATES if p in names), None)
    props = ["signal_account_id", "lifecyclestage", "signal_do_not_contact"] + ([deals_prop] if deals_prop else [])
    rows = []
    for r in hs.list_all("companies", props):
        p = r.get("properties", {})
        if not p.get("signal_account_id"):
            continue
        rows.append({
            "signal_account_id": p["signal_account_id"],
            "hubspot_id": str(r["id"]),
            "lifecyclestage": p.get("lifecyclestage"),
            "open_deals": int(float(p.get(deals_prop) or 0)) if deals_prop else 0,
            "do_not_contact": str(p.get("signal_do_not_contact", "")).lower() == "true",
            "synced_at": datetime.now(),
        })
    frame = pd.DataFrame(rows, columns=["signal_account_id", "hubspot_id", "lifecyclestage", "open_deals", "do_not_contact", "synced_at"])
    con = duckdb.connect(str(db))
    try:
        con.execute("delete from bronze.hubspot_companies")
        if len(frame):
            con.register("_f", frame)
            con.execute("insert into bronze.hubspot_companies select * from _f")
    finally:
        con.close()
    return {"status": "pulled", "companies": len(frame), "open_deals_property": deals_prop}


# ---------- push ----------

def plan(db: str | Path, as_of: date | None, today: date) -> dict:
    """Everything the push would write, computed from the warehouse as of the run day (read-only)."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        params = dict(con.execute("select param, value from seeds.scoring_params").fetchall())
        as_of = as_of or replay_date(params, today)
        profile = params["active_profile"]
        t = float(params[f"engine_threshold_{profile}"])
        warm, watch = t * float(params["warm_ratio"]), t * float(params["watch_ratio"])
        companies = _rows(con, """
            with synced as (
                select distinct account_id from gold.account_daily_scores
                where score_date between ? and ? and engine_score >= ?
                union
                select distinct account_id from gold.engine_alerts where is_active and alert_date <= ?
            ),
            last_alert as (
                select account_id, max(alert_date) as last_alert_date from gold.engine_alerts
                where is_active and alert_date <= ? group by 1
            )
            select a.account_id, a.company_name, a.domain, a.owner_ae_id, s.engine_score, s.fit_grade, s.reason,
                   x.excluded, x.reason as exclusion, l.last_alert_date
            from synced
            join staging.stg_accounts a using (account_id)
            join gold.account_daily_scores s on s.account_id = a.account_id and s.score_date = ?
            join silver.account_exclusions x on x.account_id = a.account_id
            left join last_alert l on l.account_id = a.account_id
            -- Prospects only: existing customers, competitors and the like are not pushed. Accounts a rep excluded in
            -- HubSpot (crm_*) stay in sync so their record shows why they stopped alerting.
            where not x.excluded or x.reason like 'crm_%'
            order by a.account_id
        """, [params["eval_start"], as_of, watch, as_of, as_of, as_of])
        today_alerts = _rows(con, """
            select a.account_id, c.company_name, c.people
            from gold.engine_alerts a join gold.alert_context c using (account_id, alert_date)
            where a.is_active and a.alert_date = ? order by a.engine_score desc
        """, [as_of])
    finally:
        con.close()

    def tier(row) -> str:
        if row["excluded"]:
            return "Excluded"
        s = row["engine_score"]
        return "Hot" if s >= t else "Warm" if s >= warm else "Watch" if s >= watch else "Below"

    headlines = state.narratives()
    company_rows = []
    for c in companies:
        props = {
            "name": c["company_name"],
            "domain": c["domain"] + SYNTHETIC_SUFFIX,
            "signal_score": str(round(c["engine_score"])),
            "signal_tier": tier(c),
            "signal_fit_grade": c["fit_grade"],
            "signal_reason": c["reason"] if not c["excluded"] else f"Excluded: {c['exclusion']}",
            "signal_owner_ae": c["owner_ae_id"],
        }
        if c["last_alert_date"]:
            props["signal_last_alert_date"] = str(_midnight_ms(c["last_alert_date"]))
            if len(headlines):
                h = headlines[(headlines.account_id == c["account_id"]) & (headlines.alert_date.dt.date == c["last_alert_date"])]
                if len(h):
                    props["signal_headline"] = json.loads(h.iloc[0].narrative)["headline"][:1000]
        company_rows.append((c["account_id"], props))

    contacts, tasks = [], []
    for a in today_alerts:
        for p in a["people"] or []:
            email = p["email"] + SYNTHETIC_SUFFIX
            contacts.append({"account_id": a["account_id"], "email": email, "properties": {
                "email": email, "firstname": p["first_name"], "lastname": p["last_name"], "jobtitle": p["title"]}})
        story = headlines[(headlines.account_id == a["account_id"]) & (headlines.alert_date.dt.date == as_of)] if len(headlines) else headlines
        n = json.loads(story.iloc[0].narrative) if len(story) else None
        body = "\n".join([n["headline"], *[f"- {b}" for b in n["why_now"]], f"Angle: {n['angle']}"]) if n else "See the Signal Engine alert."
        tasks.append({"account_id": a["account_id"], "properties": {
            "hs_task_subject": f"Signal Engine: reach out to {a['company_name']} (alert {as_of})",
            "hs_task_body": body[:5000],
            "hs_timestamp": str(_midnight_ms(today) + 9 * 3600 * 1000),  # due 09:00 UTC on the run day
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "HIGH",
            "hs_task_type": "TODO",
        }})
    return {"as_of": as_of, "profile": profile, "companies": company_rows, "contacts": contacts, "tasks": tasks}


def push(db: str | Path, hs: HubSpot | None, as_of: date | None = None, dry_run: bool = False,
         out_dir: Path = Path("out"), today: date | None = None) -> dict:
    p = plan(db, as_of, today or date.today())
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"hubspot_{p['as_of']}.json"
    out_file.write_text(json.dumps({**p, "companies": [{"signal_account_id": k, **v} for k, v in p["companies"]]}, indent=2, default=str))
    summary = {"as_of": p["as_of"], "companies": len(p["companies"]), "contacts": len(p["contacts"]),
               "tasks": len(p["tasks"]), "file": str(out_file)}
    if hs is None or dry_run:
        state.log_activation(p["as_of"], p["profile"], "hubspot", "dry_run", summary["tasks"], json.dumps(summary, default=str))
        return {**summary, "status": "dry_run"}

    hs.ensure_group("companies", GROUP, "Signal Engine")
    created_props = hs.ensure_properties("companies", company_properties())
    company_ids = hs.batch_upsert("companies", "signal_account_id", p["companies"])

    contact_ids = hs.batch_upsert("contacts", "email", [(c["email"], c["properties"]) for c in p["contacts"]]) if p["contacts"] else {}
    pairs = [(contact_ids[c["email"]], company_ids[c["account_id"]]) for c in p["contacts"]
             if c["email"] in contact_ids and c["account_id"] in company_ids]
    if pairs:
        hs.associate_default("contacts", "companies", pairs)

    new_tasks = [t for t in p["tasks"] if not hs.find_by("tasks", "hs_task_subject", t["properties"]["hs_task_subject"], ["hs_task_subject"])]
    task_ids = hs.batch_create("tasks", [t["properties"] for t in new_tasks]) if new_tasks else []
    task_pairs = [(tid, company_ids[t["account_id"]]) for tid, t in zip(task_ids, new_tasks) if t["account_id"] in company_ids]
    if task_pairs:
        hs.associate_default("tasks", "companies", task_pairs)

    result = {**summary, "status": "synced", "properties_created": len(created_props), "tasks_created": len(task_ids),
              "tasks_skipped_existing": len(p["tasks"]) - len(new_tasks), "api_calls": hs.calls}
    state.log_activation(p["as_of"], p["profile"], "hubspot", "synced", len(task_ids), json.dumps(result, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync with HubSpot.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("pull", help="HubSpot → warehouse (run before dbt build)")
    pl.add_argument("--db", default="data/holdout.duckdb")
    ps = sub.add_parser("push", help="warehouse → HubSpot (run after the digest)")
    ps.add_argument("--db", default="data/holdout.duckdb")
    ps.add_argument("--as-of", type=date.fromisoformat)
    ps.add_argument("--dry-run", action="store_true")
    ps.add_argument("--out", default="out")
    args = ap.parse_args()
    hs = client_from_env()
    result = pull(args.db, hs) if args.cmd == "pull" else push(args.db, hs, args.as_of, args.dry_run, Path(args.out))
    print(" · ".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    main()

