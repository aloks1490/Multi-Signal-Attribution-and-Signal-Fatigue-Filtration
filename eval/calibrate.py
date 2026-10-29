"""Threshold calibration on the dev seed. Capacity is a hard ceiling; three operating points are chosen:

- precise (`*_threshold_precise`): best F1 of account precision and recall on dev (both weighted equally).
- broad (`*_threshold_broad`): best F2 on dev (recall weighted about twice as much as precision).
- capacity (`*_threshold_capacity`): the threshold that sends the most alerts without any week exceeding
  capacity. Label-free; shows what "fill the reps' capacity" would cost in precision.

All three stay within capacity and use dev labels only; the holdout seed is never touched. Which of precise
and broad actually alerts reps is the team-level `active_profile` setting in scoring_params.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from engine.alerting import AlertRules, run_alerts
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
    """Engine alerts for any threshold, from gold.account_daily_scores (non-excluded accounts), through the same
    rules as gold.engine_alerts (engine/alerting.py: cooldown, score jump, per-AE budget).

    column: engine_score (M2) or engine_score_m1 (decay only, kept for comparison).
    """

    def __init__(self, con: duckdb.DuckDBPyConnection, column: str = "engine_score"):
        assert column in ("engine_score", "engine_score_m1")
        self.rules = AlertRules.from_params(load_params(con))
        df = con.execute(f"""
            select s.account_id, s.score_date, s.{column} as score, a.owner_ae_id
            from gold.account_daily_scores s
            join silver.account_exclusions x using (account_id)
            join staging.stg_accounts a using (account_id)
            where not x.excluded
        """).df()
        m = df.pivot(index="account_id", columns="score_date", values="score").sort_index(axis=1)
        self.scores = m.to_numpy()
        self.ids = list(m.index)
        self.owners = df.drop_duplicates("account_id").set_index("account_id").loc[m.index, "owner_ae_id"].tolist()
        self.days = [pd.Timestamp(c).date() for c in m.columns]

    def candidates(self) -> np.ndarray:
        v = self.scores[self.scores > 0]
        return np.unique(np.round(np.quantile(v, np.linspace(0.5, 1, N_CANDIDATES)), 4))

    def log(self, threshold: float) -> pd.DataFrame:
        log = run_alerts(self.scores, self.owners, self.days, threshold, self.rules)
        return log.assign(account_id=[self.ids[i] for i in log["account"]], date=[self.days[d] for d in log["day"]])

    def alerts(self, threshold: float) -> pd.DataFrame:
        log = self.log(threshold)
        hit = log[log["status"] == "alerted"]
        return pd.DataFrame({"account_id": hit["account_id"].tolist(), "alert_date": hit["date"].tolist()})


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


def f_beta(s: dict, beta: float) -> float:
    """F-beta of account precision and recall. beta=1 weighs them equally; beta=2 favours recall."""
    p, r = s["precision_accounts"], s["recall"]
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r) if p + r else 0.0


def choose(sim, truth: pd.DataFrame, window: Window, capacity: int) -> dict[str, float]:
    """Return the precise (best dev F1), broad (best dev F2) and capacity-filling thresholds, all within capacity."""
    best = {"precise": None, "broad": None, "capacity": None}
    for t in sorted(sim.candidates(), reverse=True):  # high → low so ties keep the higher threshold
        alerts = sim.alerts(t)
        if int(weekly_counts(alerts["alert_date"], window).max()) > capacity:
            continue
        s = summarize(alerts, truth, window)
        for key, value in (("precise", f_beta(s, 1)), ("broad", f_beta(s, 2)), ("capacity", s["alerts"])):
            if best[key] is None or value > best[key][1]:
                best[key] = (float(t), value)
    return {k: v[0] for k, v in best.items()}


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
        engine = choose(EngineSim(con), truth, window, capacity)
        engine_m1 = choose(EngineSim(con, "engine_score_m1"), truth, window, capacity)
        points = choose(PointsSim(con), truth, window, capacity)
    finally:
        con.close()
    result = {
        "engine_threshold_precise": engine["precise"],
        "engine_threshold_broad": engine["broad"],
        "engine_threshold_capacity": engine["capacity"],
        "engine_m1_threshold": engine_m1["precise"],
        "points_threshold_precise": points["precise"],
        "points_threshold_broad": points["broad"],
        "points_threshold_capacity": points["capacity"],
    }
    write_params(seed_csv, result)
    return result
