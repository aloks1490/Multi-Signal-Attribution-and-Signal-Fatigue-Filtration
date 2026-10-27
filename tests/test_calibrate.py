"""T-M4 and T-C: threshold selection and agreement between the Python simulation and the dbt models."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from eval.calibrate import EngineSim, PointsSim, load_params, simulate_entry_alerts
from eval.metrics import Window, weekly_counts


def test_entry_alerts_with_rearm():
    s = np.array([[5, 5, 20, 20, 5, 20, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 20]], dtype=float)
    a = simulate_entry_alerts(s, threshold=10, rearm_days=14)
    assert list(np.nonzero(a[0])[0]) == [2, 17]  # day 5 re-cross is within 14 days; day 17 is 15 days later


def test_entry_alerts_already_hot_at_start_alerts_on_day_zero():
    a = simulate_entry_alerts(np.array([[20.0, 20.0, 20.0]]), threshold=10, rearm_days=14)
    assert list(np.nonzero(a[0])[0]) == [0]


def test_m4_threshold_scan_stops_at_first_breach():
    """Busiest week rises as the threshold drops, then collapses when everything is Hot before the window."""
    from eval.calibrate import choose

    busiest = {50.0: 5, 40.0: 20, 30.0: 49, 20.0: 80, 10.0: 3}

    class Fake:
        def candidates(self):
            return np.array(sorted(busiest))

        def alerts(self, t):
            start = date(2026, 6, 29)
            return pd.DataFrame({"account_id": [f"x{i}" for i in range(busiest[t])], "alert_date": [start] * busiest[t]})

    truth = pd.DataFrame(columns=["account_id", "truth_class", "archetype", "meeting_date"])
    win = Window(date(2026, 6, 29), date(2026, 9, 27), 5)
    picked = choose(Fake(), truth, win, capacity=50)
    assert picked["capacity"] == 30.0  # most alerts within capacity, ignoring the degenerate 10.0


def test_c1_engine_sim_matches_dbt(con):
    params = load_params(con)
    sim = EngineSim(con, int(params["rearm_days"])).alerts(float(params["engine_threshold"]))
    dbt = con.execute("select account_id, alert_date from gold.engine_alerts").df()
    as_set = lambda df: set(zip(df["account_id"], pd.to_datetime(df["alert_date"]).dt.date))
    assert as_set(sim) == as_set(dbt)


def test_c2_points_sim_matches_dbt(con):
    params = load_params(con)
    sim = PointsSim(con).alerts(float(params["points_threshold"]))
    dbt = con.execute("select account_id, alert_date from gold.baseline_points_alerts").df()
    as_set = lambda df: set(zip(df["account_id"], pd.to_datetime(df["alert_date"]).dt.date))
    assert as_set(sim) == as_set(dbt)


def test_e2_engine_within_capacity(con):
    params = load_params(con)
    win = Window(date.fromisoformat(params["eval_start"]), date.fromisoformat(params["eval_end"]), 5)
    alerts = con.execute("select alert_date from gold.engine_alerts").df()
    assert weekly_counts(alerts["alert_date"], win).max() <= int(params["capacity_per_week"])


def test_e3_problem_exists_pings_dwarf_engine(con):
    pings = con.execute("select count(*) from gold.baseline_event_pings where alert_date >= '2026-06-29'").fetchone()[0]
    engine = con.execute("select count(*) from gold.engine_alerts where alert_date >= '2026-06-29'").fetchone()[0]
    assert pings >= 10 * max(engine, 1)
