"""Frontend-agnostic data access for the app (Streamlit now, Reflex later).

Rules: no UI imports, every function opens the warehouse read-only and closes it before returning
(DuckDB allows one writer or many readers; dbt must be able to write while the app is running).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from eval import report
from eval.calibrate import EngineSim, load_params, window_from
from eval.metrics import summarize, weekly_counts

ROOT = Path(__file__).resolve().parent.parent
N_AES = 5
PROFILES = ("precise", "broad")
PROFILE_LABELS = {"precise": "Precise: fewer, surer alerts", "broad": "Broad: catch more buyers"}
POSITIVE_CLASSES = ("planted_buyer", "random_converter")


def databases() -> dict[str, Path]:
    """Warehouses the app can show. SIGNAL_APP_DBS="name=path,name=path" overrides the default data/ files."""
    spec = os.environ.get("SIGNAL_APP_DBS")
    if spec:
        pairs = (item.split("=", 1) for item in spec.split(",") if item)
        return {name: Path(path) for name, path in pairs}
    found = {name: ROOT / "data" / f"{name}.duckdb" for name in ("holdout", "dev")}
    return {k: v for k, v in found.items() if v.exists()}


@contextmanager
def connect(db: str | Path):
    con = duckdb.connect(str(db), read_only=True)
    try:
        yield con
    finally:
        con.close()


def df(db: str | Path, sql: str, args: list | None = None) -> pd.DataFrame:
    with connect(db) as con:
        return con.execute(sql, args or []).df()


def params(db: str | Path) -> dict[str, str]:
    with connect(db) as con:
        return load_params(con)


def thresholds(db: str | Path) -> dict[str, float]:
    p = params(db)
    return {prof: float(p[f"engine_threshold_{prof}"]) for prof in PROFILES}


def window(db: str | Path):
    return window_from(params(db), N_AES)


# ---------- overview ----------

def evaluation(db: str | Path) -> dict:
    """Full evaluation (all methods, labels). Heavy: callers should cache it."""
    return report.evaluate(str(db), N_AES)


def method_rows(ev: dict) -> pd.DataFrame:
    rows = []
    for name, s in ev["rows"].items():
        rows.append({
            "method": name,
            "alerts": s["alerts"],
            "alerts_per_ae_week": round(s["alerts_per_ae_week"], 2),
            "busiest_week": s["busiest_week"],
            "precision_accounts": s["precision_accounts"],
            "recall": s["recall"],
            "caught": len(s["caught_ids"]),
            "positives": s["positives"],
            "median_lead_days": s["median_lead_days"],
        })
    return pd.DataFrame(rows)


def profile_summary(ev: dict) -> pd.DataFrame:
    """One row per engine profile plus the per-event baseline, for the explore toggle."""
    names = {"pings": "Per-event pings", "precise": "Engine M2 precise (F1)", "broad": "Engine M2 broad (F2)"}
    rows = method_rows(ev).set_index("method")
    out = rows.loc[list(names.values())].reset_index()
    out.insert(0, "key", list(names))
    return out


def weekly_alerts(db: str | Path, profile: str) -> pd.DataFrame:
    """Alerts per week for the per-event baseline, static points, M1 and M2 at the chosen profile."""
    label = "precise (F1)" if profile == "precise" else "broad (F2)"
    keep = ["Per-event pings", f"Static points {label}", "Engine M1 precise (F1)", f"Engine M2 {label}"]
    with connect(db) as con:
        p = load_params(con)
        win = window_from(p, N_AES)
        alerts = report.method_alerts(con, p)
    frames = []
    for name in keep:
        counts = weekly_counts(alerts[name]["alert_date"], win)
        frames.append(pd.DataFrame({
            "week_start": [win.start + timedelta(days=7 * w) for w in counts.index],
            "method": name,
            "alerts": counts.values,
        }))
    return pd.concat(frames, ignore_index=True)


def positives_caught(ev: dict, profile: str) -> pd.DataFrame:
    """Each real buyer and how many days before the meeting each method first flagged it (None = missed)."""
    label = "precise (F1)" if profile == "precise" else "broad (F2)"
    methods = ["Per-event pings", f"Static points {label}", f"Engine M2 {label}"]
    pos = ev["positives"][["account_id", "truth_class", "archetype", "meeting_date"]].copy()
    for m in methods:
        lab = ev["labelled"][m]
        lead = lab[lab["outcome"] == "tp"].groupby("account_id")["lead_days"].max()
        pos[m] = pos["account_id"].map(lead)
    pos["archetype"] = pos["archetype"].where(pos["archetype"].notna(), "no signal")
    return pos.sort_values("meeting_date").reset_index(drop=True)


def hard_negatives(ev: dict, profile: str) -> pd.DataFrame:
    """Look-alike accounts (not buyers) that each method alerted on, by type."""
    label = "precise (F1)" if profile == "precise" else "broad (F2)"
    methods = ["Per-event pings", f"Static points {label}", "Engine M1 precise (F1)", f"Engine M2 {label}"]
    truth = ev["truth"]
    neg = truth[truth["truth_class"] == "hard_negative"]
    out = neg.groupby("archetype").size().rename("planted").to_frame()
    for m in methods:
        lab = ev["labelled"][m]
        hit = lab[lab["truth_class"].eq("hard_negative")].groupby("archetype")["account_id"].nunique()
        out[m] = hit.reindex(out.index, fill_value=0)
    return out.reset_index().rename(columns={"archetype": "look-alike type"})


def threshold_curve(db: str | Path) -> pd.DataFrame:
    """Precision and recall of engine M2 across thresholds (the explore slider). Heavy: cache it."""
    with connect(db) as con:
        p = load_params(con)
        win = window_from(p, N_AES)
        truth = con.execute("select * from labels.account_truth").df()
        sim = EngineSim(con, int(p["rearm_days"]))
    rows = []
    for t in sim.candidates()[::4]:
        s = summarize(sim.alerts(t), truth, win)
        rows.append({"threshold": float(t), "alerts": s["alerts"], "precision": s["precision_accounts"], "recall": s["recall"]})
    return pd.DataFrame(rows)


def alerts_at_threshold(db: str | Path, threshold: float) -> dict:
    with connect(db) as con:
        p = load_params(con)
        win = window_from(p, N_AES)
        truth = con.execute("select * from labels.account_truth").df()
        alerts = EngineSim(con, int(p["rearm_days"])).alerts(threshold)
    return summarize(alerts, truth, win)


# ---------- alert feed ----------

def alert_feed(db: str | Path, profile: str, as_of: date, days: int = 7, ae: str | None = None) -> pd.DataFrame:
    sql = """
        select a.alert_date, a.account_id, c.company_name, a.owner_ae_id, f.fit_grade,
               round(a.engine_score, 1) as score, a.reason, a.is_active
        from gold.engine_alerts a
        join staging.stg_accounts c using (account_id)
        join silver.account_fit f using (account_id)
        where a.profile = ? and a.alert_date between ? and ?
    """
    args: list = [profile, as_of - timedelta(days=days - 1), as_of]
    if ae:
        sql += " and a.owner_ae_id = ?"
        args.append(ae)
    return df(db, sql + " order by a.alert_date desc, a.engine_score desc", args)


def watchlist(db: str | Path, profile: str, as_of: date, ae: str | None = None) -> pd.DataFrame:
    """Hot / Warm / Watch tiers on one day for non-excluded accounts. Only Hot entries ping; the rest are visible here."""
    p = params(db)
    t = float(p[f"engine_threshold_{profile}"])
    warm, watch = t * float(p["warm_ratio"]), t * float(p["watch_ratio"])
    sql = """
        select s.account_id, c.company_name, c.owner_ae_id, s.fit_grade, round(s.engine_score, 1) as score,
               case when s.engine_score >= ? then 'Hot' when s.engine_score >= ? then 'Warm' else 'Watch' end as tier,
               s.reason
        from gold.account_daily_scores s
        join silver.account_exclusions x using (account_id)
        join staging.stg_accounts c using (account_id)
        where s.score_date = ? and not x.excluded and s.engine_score >= ?
    """
    args: list = [t, warm, as_of, watch]
    if ae:
        sql += " and c.owner_ae_id = ?"
        args.append(ae)
    return df(db, sql + " order by s.engine_score desc", args)


def owners(db: str | Path) -> list[str]:
    return df(db, "select distinct owner_ae_id from staging.stg_accounts order by 1")["owner_ae_id"].tolist()


# ---------- account deep-dive ----------

def account_list(db: str | Path) -> pd.DataFrame:
    """Accounts for the picker, most interesting first (alerted or highest peak score)."""
    return df(db, """
        select c.account_id, c.company_name, f.fit_grade, x.reason as exclusion,
               t.truth_class, t.archetype, max(s.engine_score) as peak_score
        from staging.stg_accounts c
        join silver.account_fit f using (account_id)
        join silver.account_exclusions x using (account_id)
        join gold.account_daily_scores s using (account_id)
        left join labels.account_truth t using (account_id)
        group by all
        order by peak_score desc
    """)


def account_profile(db: str | Path, account_id: str) -> dict:
    row = df(db, """
        select c.*, f.fit_points, f.fit_grade, f.fit_multiplier, x.excluded, x.reason as exclusion,
               t.truth_class, t.archetype, t.intent_start_date, t.meeting_date
        from staging.stg_accounts c
        join silver.account_fit f using (account_id)
        join silver.account_exclusions x using (account_id)
        left join labels.account_truth t using (account_id)
        where c.account_id = ?
    """, [account_id])
    return row.iloc[0].to_dict() if len(row) else {}


def score_history(db: str | Path, account_id: str) -> pd.DataFrame:
    return df(db, """
        select score_date, engine_score, engine_score_m1, activity_score, trigger_score, combo_bonus,
               m_breadth, m_sources, m_spike, m_gate, people_14d, sources_14d, spike_ratio, combos, reason
        from gold.account_daily_scores where account_id = ? order by score_date
    """, [account_id])


def account_alerts(db: str | Path, account_id: str) -> pd.DataFrame:
    return df(db, "select profile, alert_date, engine_score, reason from gold.engine_alerts where account_id = ? order by alert_date",
              [account_id])


def score_breakdown(db: str | Path, account_id: str, on: date) -> pd.DataFrame:
    """The M2 formula applied step by step for one account and day. The last row equals engine_score."""
    r = df(db, "select * from gold.account_daily_scores where account_id = ? and score_date = ?", [account_id, on])
    if r.empty:
        return pd.DataFrame(columns=["step", "detail", "value"])
    r = r.iloc[0]
    steps = []
    v = r["activity_score"]
    steps.append(("Activity (decayed)", "sum of weight × 2^(−age / half-life)", v))
    for col, label, detail in (
        ("m_breadth", "× breadth", f"{int(r['people_14d'])} people with mid/bottom-funnel activity"),
        ("m_sources", "× sources", f"{int(r['sources_14d'])} channels"),
        ("m_spike", "× spike", f"{r['spike_ratio']:.1f}× usual weekly activity"),
        ("m_gate", "× high-intent gate", "no bottom-funnel activity in 14 days" if r["m_gate"] < 1 else "bottom-funnel activity present"),
    ):
        v = v * r[col]
        steps.append((f"{label} ({r[col]:.2f})", detail, v))
    v = v + r["trigger_score"]
    steps.append(("+ triggers (decayed)", "funding, hires, job posts, tool changes", v))
    v = v + r["combo_bonus"]
    steps.append(("+ combos", r["combos"] or "none", v))
    v = v * r["fit_multiplier"]
    steps.append((f"× fit {r['fit_grade']} ({r['fit_multiplier']:.2f})", "ICP gate", v))
    return pd.DataFrame(steps, columns=["step", "detail", "value"])


def account_events(db: str | Path, account_id: str) -> pd.DataFrame:
    """Every scorable event and trigger at the account, with a readable person label."""
    return df(db, """
        select e.occurred_at, e.event_type, e.funnel_stage, e.source, e.weight, e.half_life_days,
               coalesce(c.first_name || ' ' || c.last_name || ' · ' || c.title,
                        case when e.person_key like 'anon:%' then 'Anonymous visitor ' || right(e.person_key, 4)
                             else replace(e.person_key, 'email:', '') end) as person
        from silver.events_clean e
        left join staging.stg_contacts c on c.contact_id = e.contact_id
        where e.account_id = ?
        union all
        select t.occurred_at, t.trigger_type, 'TRIGGER', 'enrichment', t.weight, t.half_life_days, 'Company: ' || t.detail
        from silver.triggers_clean t
        where t.account_id = ?
        order by 1
    """, [account_id, account_id])


def signal_contributions(db: str | Path, account_id: str, on: date) -> pd.DataFrame:
    return df(db, """
        select event_type as signal, 'engagement' as kind, contribution, n_events
        from gold.int_engagement_contrib where account_id = ? and score_date = ?
        union all
        select trigger_type, 'trigger', contribution, n_events
        from gold.int_trigger_contrib where account_id = ? and score_date = ?
        order by contribution desc
    """, [account_id, on, account_id, on])


def decay_curves(events: pd.DataFrame, on: date, top_n: int = 6, horizon_days: int = 30) -> pd.DataFrame:
    """Contribution of the biggest events over time, from when they happened until horizon_days after `on`."""
    if events.empty:
        return pd.DataFrame(columns=["event", "date", "contribution"])
    ev = events[pd.to_datetime(events["occurred_at"]).dt.date < on].copy()
    if ev.empty:
        return pd.DataFrame(columns=["event", "date", "contribution"])
    age = (pd.Timestamp(on) - pd.to_datetime(ev["occurred_at"])).dt.total_seconds() / 86400
    ev["now"] = ev["weight"] * np.power(2.0, -age / ev["half_life_days"])
    ev = ev.sort_values("now", ascending=False).head(top_n)
    rows = []
    for _, e in ev.iterrows():
        start = pd.to_datetime(e["occurred_at"])
        label = f"{e['event_type']} · {pd.Timestamp(start).date()}"
        for d in range(0, (pd.Timestamp(on) - start.normalize()).days + horizon_days):
            day = start.normalize() + pd.Timedelta(days=d)
            a = max((day - start).total_seconds() / 86400, 0)
            rows.append({"event": label, "date": day.date(), "contribution": e["weight"] * 2 ** (-a / e["half_life_days"])})
    return pd.DataFrame(rows)
