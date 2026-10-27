"""Threshold calibration on the dev seed. Capacity is a hard ceiling; two operating points are chosen:

- deployed (`engine_threshold`, `points_threshold`): best F1 of account precision and recall on dev,
  among thresholds whose busiest week stays within capacity. Uses dev labels; holdout is never touched.
- capacity (`*_threshold_capacity`): the threshold that sends the most alerts without any week exceeding
  capacity. Label-free; shows what "fill the reps' capacity" would cost in precision.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from eval.metrics import Window, summarize, weekly_counts

N_CANDIDATES = 400


def load_params(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return dict(con.execute("select param, value from seeds.scoring_params").fetchall())


def window_from(params: dict[str, str], n_aes: int) -> Window:
    return Window(date.fromisoformat(params["eval_start"]), date.fromisoformat(params["eval_end"]), n_aes)


def simulate_entry_alerts(scores: np.ndarray, threshold: float, rearm_days: int) -> np.ndarray:
    """Alert-on-entry with re-arm, matching gold.engine_alerts.

    scores: accounts × consecutive days. Returns a boolean matrix of alert days.
    """
    hot = scores >= threshold
    prev = np.zeros(scores.shape[0], dtype=bool)
    last_alert = np.full(scores.shape[0], -10**9)
    alerts = np.zeros_like(hot)
    for t in range(scores.shape[1]):
        entry = hot[:, t] & ~prev
        fire = entry & (t - last_alert >= rearm_days)
        alerts[:, t] = fire
        last_alert = np.where(fire, t, last_alert)
        prev = hot[:, t]
    return alerts


class EngineSim:
    """Engine alerts for any threshold, from gold.account_daily_scores (non-excluded accounts)."""

    def __init__(self, con: duckdb.DuckDBPyConnection, rearm_days: int):
        df = con.execute("""
            select s.account_id, s.score_date, s.engine_score
            from gold.account_daily_scores s
            join silver.account_exclusions x using (account_id)
            where not x.excluded
        """).df()
        m = df.pivot(index="account_id", columns="score_date", values="engine_score").sort_index(axis=1)
        self.scores = m.to_numpy()
        self.ids = list(m.index)
        self.days = [pd.Timestamp(c).date() for c in m.columns]
        self.rearm_days = rearm_days

    def candidates(self) -> np.ndarray:
        v = self.scores[self.scores > 0]
        return np.unique(np.round(np.quantile(v, np.linspace(0.5, 1, N_CANDIDATES)), 4))

    def alerts(self, threshold: float) -> pd.DataFrame:
        rows, cols = np.nonzero(simulate_entry_alerts(self.scores, threshold, self.rearm_days))
        return pd.DataFrame({
            "account_id": [self.ids[i] for i in rows],
            "alert_date": [self.days[j] for j in cols],
        })


class PointsSim:
    """Static-points (no decay) MQL alerts for any threshold, matching gold.baseline_points_alerts."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        ev = con.execute("""
            with pts as (
                select account_id, known_at as ts, event_id, weight from silver.events_clean where category = 'engagement'
                union all
                select account_id, occurred_at, event_id, weight from silver.triggers_clean
            )
            select p.*, sum(weight) over (partition by account_id order by ts, event_id
                                          rows between unbounded preceding and current row) as cum_points
            from pts p
            join silver.account_exclusions x using (account_id)
            where not x.excluded
            order by account_id, ts, event_id
        """).df()
        self.per_account = {k: (g["cum_points"].to_numpy(), g["ts"].to_numpy()) for k, g in ev.groupby("account_id")}

    def candidates(self) -> np.ndarray:
        finals = np.array([cum.max() for cum, _ in self.per_account.values()])
        return np.unique(np.round(np.quantile(finals[finals > 0], np.linspace(0, 1, N_CANDIDATES)), 4))

    def alerts(self, threshold: float) -> pd.DataFrame:
        rows = []
        for account_id, (cum, ts) in self.per_account.items():
            i = np.searchsorted(cum, threshold, side="left")
            if i < len(cum):
                rows.append((account_id, pd.Timestamp(ts[i]).date() + timedelta(days=1)))
        return pd.DataFrame(rows, columns=["account_id", "alert_date"])


def f1(s: dict) -> float:
    p, r = s["precision_accounts"], s["recall"]
    return 2 * p * r / (p + r) if p + r else 0.0


def choose(sim, truth: pd.DataFrame, window: Window, capacity: int) -> dict[str, float]:
    """Return the deployed (best dev F1) and capacity-filling thresholds, both within capacity."""
    best_f1, best_vol = None, None
    for t in sorted(sim.candidates(), reverse=True):  # high → low so ties keep the higher threshold
        alerts = sim.alerts(t)
        if int(weekly_counts(alerts["alert_date"], window).max()) > capacity:
            continue
        s = summarize(alerts, truth, window)
        if best_f1 is None or f1(s) > best_f1[1]:
            best_f1 = (float(t), f1(s))
        if best_vol is None or s["alerts"] > best_vol[1]:
            best_vol = (float(t), s["alerts"])
    return {"deployed": best_f1[0], "capacity": best_vol[0]}


def write_params(seed_csv: Path, updates: dict[str, float]) -> None:
    rows = list(csv.DictReader(seed_csv.open()))
    for r in rows:
        if r["param"] in updates:
            r["value"] = f"{updates[r['param']]:.4f}"
    with seed_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["param", "value"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run(db: str, seed_csv: Path, n_aes: int) -> dict[str, float]:
    con = duckdb.connect(db, read_only=True)
    try:
        params = load_params(con)
        window = window_from(params, n_aes)
        capacity = int(params["capacity_per_week"])
        truth = con.execute("select * from labels.account_truth").df()
        engine = choose(EngineSim(con, int(params["rearm_days"])), truth, window, capacity)
        points = choose(PointsSim(con), truth, window, capacity)
    finally:
        con.close()
    result = {
        "engine_threshold": engine["deployed"],
        "engine_threshold_capacity": engine["capacity"],
        "points_threshold": points["deployed"],
        "points_threshold_capacity": points["capacity"],
    }
    write_params(seed_csv, result)
    return result
