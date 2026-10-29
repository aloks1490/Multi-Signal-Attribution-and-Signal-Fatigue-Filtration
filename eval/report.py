"""Results tables: per-event pings vs static points vs engine, plus hard negatives and misses."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from eval.calibrate import EngineSim, PointsSim, load_params, window_from
from eval.metrics import label_alerts, positives, summarize, weekly_counts

PROFILE_LABEL = {"precise": "precise (F1)", "broad": "broad (F2)"}
BUDGETS = (15, 25, 40, 60)  # alerts over the whole evaluation window


def budget_table(con: duckdb.DuckDBPyConnection, params: dict[str, str], truth: pd.DataFrame, window) -> dict[str, dict[int, dict]]:
    """Each method at the same alert volume. The threshold is the one whose in-window alert count is closest to
    the budget, chosen from counts alone (no labels), so this comparison is fair on the holdout seed too."""
    sims = {
        "Static points": PointsSim(con),
        "Engine M1": EngineSim(con, "engine_score_m1"),
        "Engine M2": EngineSim(con),
    }
    out: dict[str, dict[int, dict]] = {}
    for name, sim in sims.items():
        by_count = {}
        for t in sim.candidates():
            a = sim.alerts(t)
            a = a[(pd.to_datetime(a["alert_date"]).dt.date >= window.start) & (pd.to_datetime(a["alert_date"]).dt.date <= window.end)]
            by_count.setdefault(len(a), a)
        out[name] = {}
        for b in BUDGETS:
            n = min(by_count, key=lambda c: (abs(c - b), c))
            out[name][b] = summarize(by_count[n], truth, window)
    return out


def _profile(con: duckdb.DuckDBPyConnection, table: str, profile: str) -> pd.DataFrame:
    return con.execute(f"select account_id, alert_date from gold.{table} where profile = ?", [profile]).df()


def active_engine(params: dict[str, str]) -> str:
    return f"Engine M2 {PROFILE_LABEL[params['active_profile']]}"


def method_alerts(con: duckdb.DuckDBPyConnection, params: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Deployed thresholds come from the dbt tables; capacity-filling ones are simulated with the same rules."""
    return {
        "Per-event pings": con.execute("select account_id, alert_date from gold.baseline_event_pings").df(),
        "Static points @ capacity": PointsSim(con).alerts(float(params["points_threshold_capacity"])),
        "Static points precise (F1)": _profile(con, "baseline_points_alerts", "precise"),
        "Static points broad (F2)": _profile(con, "baseline_points_alerts", "broad"),
        "Engine M1 precise (F1)": EngineSim(con, "engine_score_m1").alerts(float(params["engine_m1_threshold"])),
        "Engine M2 @ capacity": EngineSim(con).alerts(float(params["engine_threshold_capacity"])),
        "Engine M2 precise (F1)": _profile(con, "engine_alerts", "precise"),
        "Engine M2 broad (F2)": _profile(con, "engine_alerts", "broad"),
    }


def evaluate(db: str, n_aes: int) -> dict:
    con = duckdb.connect(db, read_only=True)
    try:
        params = load_params(con)
        window = window_from(params, n_aes)
        truth = con.execute("select * from labels.account_truth").df()
        rows, labelled = {}, {}
        for name, alerts in method_alerts(con, params).items():
            rows[name] = summarize(alerts, truth, window)
            rows[name]["busiest_week"] = int(weekly_counts(alerts["alert_date"], window).max())
            labelled[name] = label_alerts(alerts, truth, window).merge(truth[["account_id", "truth_class", "archetype"]], on="account_id")
        budgets = budget_table(con, params, truth, window)
        decisions = con.execute("""
            select profile, status, count(*) as n from gold.alert_candidates
            where score_date between ? and ? group by 1, 2 order by 1, 2""", [window.start, window.end]).df()
        handraises = con.execute(
            "select count(*) from gold.handraise_routes where routed_date between ? and ?", [window.start, window.end]
        ).fetchone()[0]
        return {
            "params": params,
            "window": window,
            "truth": truth,
            "rows": rows,
            "labelled": labelled,
            "handraises": handraises,
            "budgets": budgets,
            "decisions": decisions,
            "positives": positives(truth, window),
        }
    finally:
        con.close()


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def section(name: str, seed_note: str, r: dict) -> str:
    w, p = r["window"], r["params"]
    out = [f"## {name} ({seed_note})", ""]
    out.append(f"Window {w.start} → {w.end} ({w.n_weeks:.0f} weeks), {w.n_aes} AEs, capacity {p['capacity_per_week']}/week. "
               f"Thresholds (precise F1 / broad F2 / capacity): engine M2 {float(p['engine_threshold_precise']):.2f} / "
               f"{float(p['engine_threshold_broad']):.2f} / {float(p['engine_threshold_capacity']):.2f}, "
               f"static points {float(p['points_threshold_precise']):.2f} / {float(p['points_threshold_broad']):.2f} / "
               f"{float(p['points_threshold_capacity']):.2f}, engine M1 (F1) {float(p['engine_m1_threshold']):.2f}. "
               f"Active profile (what reps receive): **{p['active_profile']}**. "
               f"Positives: {len(r['positives'])}.")
    out += ["", "| Method | Alerts | Alerts/AE/week | Busiest week | Precision (alerts) | Precision (accounts) | Recall | Median lead (days) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for m, s in r["rows"].items():
        lead = "–" if s["median_lead_days"] is None else f"{s['median_lead_days']:.0f}"
        out.append(f"| {m} | {s['alerts']:,} | {s['alerts_per_ae_week']:.1f} | {s['busiest_week']} | {_pct(s['precision_alerts'])} | "
                   f"{_pct(s['precision_accounts'])} | {_pct(s['recall'])} ({len(s['caught_ids'])}/{s['positives']}) | {lead} |")
    out += ["", f"Hand-raises routed outside scoring (demo requests): {r['handraises']}. "
            f"Post-meeting alerts dropped from metrics: " +
            ", ".join(f"{m} {s['post_meeting_alerts']}" for m, s in r["rows"].items()) + "."]

    # What the cooldown and per-AE budget held back (engine M2).
    d = r["decisions"].pivot_table(index="profile", columns="status", values="n", fill_value=0)
    cols = [c for c in ("alerted", "cooldown", "deferred", "dropped", "expired") if c in d.columns]
    out += ["", f"**Alerting decisions, engine M2** (cooldown {p['cooldown_days']} days, jump ×{p['jump_ratio']}, "
            f"budget {p['ae_daily_budget']}/AE/day and {p['ae_weekly_budget']}/AE/week, defer up to {p['defer_days']} days)", "",
            "| Profile | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
    for prof, row in d.iterrows():
        out.append(f"| {prof} | " + " | ".join(str(int(row[c])) for c in cols) + " |")

    # Same alert volume for every method: the fair way to compare ranking quality.
    out += ["", "**Equal alert budget** (threshold set by alert count alone; precision is per account)", "",
            "| Alerts in window | " + " | ".join(f"{m}: precision / recall" for m in r["budgets"]) + " |",
            "|---:|" + "---:|" * len(r["budgets"])]
    for b in BUDGETS:
        cells = [f"{_pct(v[b]['precision_accounts'])} / {_pct(v[b]['recall'])} (n={v[b]['alerts']})" for v in r["budgets"].values()]
        out.append(f"| ~{b} | " + " | ".join(cells) + " |")

    # Hard negatives alerted (distinct accounts), by type.
    neg_types = sorted(r["truth"].loc[r["truth"]["truth_class"] == "hard_negative", "archetype"].dropna().unique())
    out += ["", "**Hard-negative accounts alerted** (distinct accounts, of those planted per type)", "",
            "| Type | Planted | " + " | ".join(r["rows"]) + " |", "|---|---:|" + "---:|" * len(r["rows"])]
    planted = r["truth"][r["truth"]["truth_class"] == "hard_negative"].groupby("archetype").size()
    for t in neg_types:
        cells = []
        for m in r["rows"]:
            lab = r["labelled"][m]
            cells.append(str(lab.loc[lab["archetype"].eq(t) & lab["truth_class"].eq("hard_negative"), "account_id"].nunique()))
        out.append(f"| {t} | {planted.get(t, 0)} | " + " | ".join(cells) + " |")

    # Positives the active engine profile missed.
    active = active_engine(p)
    eng = r["rows"][active]
    missed = r["positives"][~r["positives"]["account_id"].isin(eng["caught_ids"])]
    out += ["", f"**Positives missed by {active} (active profile):** {len(missed)}", ""]
    if len(missed):
        out += ["| Account | Class | Archetype | Meeting |", "|---|---|---|---|"]
        for _, row in missed.sort_values("meeting_date").iterrows():
            out.append(f"| {row['account_id']} | {row['truth_class']} | {row['archetype'] if isinstance(row['archetype'], str) else '–'} | {row['meeting_date']} |")
    return "\n".join(out)


def write(runs: dict[str, tuple[str, str]], out: Path, n_aes: int) -> str:
    parts = ["# Results", "",
             f"Generated {date.today().isoformat()} by `python -m eval report`. Synthetic data: these numbers show the machinery works, "
             "not that the weights hold on real data. \"precise (F1)\" and \"broad (F2)\" thresholds were tuned on the dev seed "
             "(F1 weighs precision and recall equally; F2 weighs recall about twice as much) under a hard ceiling of 50 alerts/week, "
             "and applied unchanged to the holdout seed. \"@ capacity\" rows use the label-free threshold that sends the most "
             "alerts without breaching the ceiling. Precision is per account unless stated.", ""]
    for name, (db, note) in runs.items():
        parts += [section(name, note, evaluate(db, n_aes)), ""]
    text = "\n".join(parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text


def weekly_table(db: str, n_aes: int) -> pd.DataFrame:
    """Alerts per week per method (used by the app later)."""
    con = duckdb.connect(db, read_only=True)
    try:
        params = load_params(con)
        window = window_from(params, n_aes)
        return pd.DataFrame({m: weekly_counts(a["alert_date"], window) for m, a in method_alerts(con, params).items()})
    finally:
        con.close()
