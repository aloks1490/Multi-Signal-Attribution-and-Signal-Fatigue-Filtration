"""Results tables: per-event pings vs static points vs engine, plus hard negatives and misses."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from eval.calibrate import EngineSim, PointsSim, load_params, window_from
from eval.metrics import label_alerts, positives, summarize, weekly_counts

ENGINE = "Engine M1"


def method_alerts(con: duckdb.DuckDBPyConnection, params: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Deployed thresholds come from the dbt tables; capacity-filling ones are simulated with the same rules."""
    return {
        "Per-event pings": con.execute("select account_id, alert_date from gold.baseline_event_pings").df(),
        "Static points @ capacity": PointsSim(con).alerts(float(params["points_threshold_capacity"])),
        "Static points @ dev F1": con.execute("select account_id, alert_date from gold.baseline_points_alerts").df(),
        "Engine M1 @ capacity": EngineSim(con, int(params["rearm_days"])).alerts(float(params["engine_threshold_capacity"])),
        ENGINE: con.execute("select account_id, alert_date from gold.engine_alerts").df(),
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
               f"Thresholds (dev F1 / capacity): engine {float(p['engine_threshold']):.2f} / {float(p['engine_threshold_capacity']):.2f}, "
               f"static points {float(p['points_threshold']):.2f} / {float(p['points_threshold_capacity']):.2f}. "
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

    # Positives the engine missed.
    eng = r["rows"][ENGINE]
    missed = r["positives"][~r["positives"]["account_id"].isin(eng["caught_ids"])]
    out += ["", f"**Positives the engine missed:** {len(missed)}", ""]
    if len(missed):
        out += ["| Account | Class | Archetype | Meeting |", "|---|---|---|---|"]
        for _, row in missed.sort_values("meeting_date").iterrows():
            out.append(f"| {row['account_id']} | {row['truth_class']} | {row['archetype'] if isinstance(row['archetype'], str) else '–'} | {row['meeting_date']} |")
    return "\n".join(out)


def write(runs: dict[str, tuple[str, str]], out: Path, n_aes: int) -> str:
    parts = ["# Results", "",
             f"Generated {date.today().isoformat()} by `python -m eval report`. Synthetic data: these numbers show the machinery works, "
             "not that the weights hold on real data. Deployed thresholds (\"@ dev F1\" and \"Engine M1\") were tuned for F1 on the dev seed "
             "under a hard ceiling of 50 alerts/week and applied unchanged to the holdout seed. \"@ capacity\" rows use the label-free "
             "threshold that sends the most alerts without breaching the ceiling.", ""]
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
