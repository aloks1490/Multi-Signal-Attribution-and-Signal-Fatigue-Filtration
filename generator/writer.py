"""Write the generated world to DuckDB: bronze.* (what a company would have) and labels.* (the truth)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from generator.world import World

BRONZE_TABLES = ("accounts", "contacts", "ip_company_map", "web_events", "product_events", "marketing_events", "trigger_events")


def _events(rows: list[dict], prefix: str, sort_cols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"])
    df = df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    df.insert(0, "event_id", [f"{prefix}_{i + 1:07d}" for i in range(len(df))])
    return df


def frames(w: World) -> dict[str, pd.DataFrame]:
    accounts = pd.DataFrame([{
        "account_id": a.account_id,
        "company_name": a.company_name,
        "domain": a.domain,
        "industry": a.industry,
        "employee_count": a.employee_count,
        "sales_headcount": a.sales_headcount,
        "region": a.region,
        "crm": a.crm,
        "tech_stack": a.tech_stack,
        "customer_status": a.customer_status,
        "is_competitor": a.is_competitor,
        "has_open_deal": a.has_open_deal,
        "do_not_contact": a.do_not_contact,
        "owner_ae_id": a.owner_ae_id,
    } for a in w.accounts])

    contacts = pd.DataFrame([{
        "contact_id": c.contact_id,
        "account_id": c.account_id,
        "email": c.email,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "title": c.title,
        "seniority": c.seniority,
        "function": c.function,
    } for a in w.accounts for c in a.contacts])

    ip_map = pd.DataFrame([{"ip": ip, "domain": a.domain} for a in w.accounts for ip in a.ips])

    web = _events(w.web, "w", ["occurred_at", "anonymous_id", "page_path"])
    product = _events(w.product, "p", ["occurred_at", "user_email", "event_name"])
    marketing = _events(w.marketing, "m", ["occurred_at", "contact_email", "event_name"])
    triggers = _events(w.triggers, "t", ["occurred_at", "account_domain", "trigger_type"])
    triggers["closed_at"] = pd.to_datetime(triggers["closed_at"])

    truth = pd.DataFrame([
        w.truth.get(a.account_id, {
            "account_id": a.account_id,
            "truth_class": "noise",
            "archetype": None,
            "intent_start_date": None,
            "meeting_date": None,
        })
        for a in w.accounts
    ])
    truth["intent_start_date"] = pd.to_datetime(truth["intent_start_date"]).dt.date
    truth["meeting_date"] = pd.to_datetime(truth["meeting_date"]).dt.date

    return {
        "bronze.accounts": accounts,
        "bronze.contacts": contacts,
        "bronze.ip_company_map": ip_map,
        "bronze.web_events": web,
        "bronze.product_events": product,
        "bronze.marketing_events": marketing,
        "bronze.trigger_events": triggers,
        "labels.account_truth": truth,
    }


def write(w: World, db_path: str | Path) -> dict[str, int]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # a fresh world per run; dbt rebuilds everything downstream
    con = duckdb.connect(str(db_path))
    counts = {}
    try:
        con.execute("CREATE SCHEMA bronze")
        con.execute("CREATE SCHEMA labels")
        for name, df in frames(w).items():
            con.register("_df", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
            counts[name] = len(df)
        # The CRM export lands here (activation/crm.py pull). Empty until HubSpot is connected, but always present
        # so dbt has a stable source.
        con.execute("""CREATE TABLE bronze.hubspot_companies (
            signal_account_id VARCHAR, hubspot_id VARCHAR, lifecyclestage VARCHAR, open_deals INTEGER,
            do_not_contact BOOLEAN, synced_at TIMESTAMP)""")
        counts["bronze.hubspot_companies"] = 0
        con.execute("ALTER TABLE labels.account_truth ALTER intent_start_date TYPE DATE")
        con.execute("ALTER TABLE labels.account_truth ALTER meeting_date TYPE DATE")
    finally:
        con.close()
    return counts
