"""T-M: alert labelling and summary metrics on toy data."""
from __future__ import annotations

from datetime import date

import pandas as pd

from eval.metrics import Window, label_alerts, summarize, weekly_counts

WIN = Window(date(2026, 6, 29), date(2026, 9, 27), n_aes=5)
TRUTH = pd.DataFrame([
    {"account_id": "buyer", "truth_class": "planted_buyer", "archetype": "committee", "meeting_date": date(2026, 8, 31)},
    {"account_id": "buyer2", "truth_class": "planted_buyer", "archetype": "quiet", "meeting_date": date(2026, 9, 15)},
    {"account_id": "noise", "truth_class": "noise", "archetype": None, "meeting_date": None},
])


def alerts(*rows):
    return pd.DataFrame(rows, columns=["account_id", "alert_date"])


def test_m1_tp_window_boundaries():
    a = alerts(
        ("buyer", date(2026, 8, 30)),  # 1 day before → tp
        ("buyer", date(2026, 8, 31)),  # meeting day → post_meeting
        ("buyer", date(2026, 7, 1)),   # 61 days before → fp
        ("buyer", date(2026, 7, 2)),   # 60 days before → tp
        ("noise", date(2026, 8, 1)),   # fp
    )
    out = label_alerts(a, TRUTH, WIN).set_index("alert_date")["outcome"]
    assert out[date(2026, 8, 30)] == "tp"
    assert out[date(2026, 8, 31)] == "post_meeting"
    assert out[date(2026, 7, 1)] == "fp"
    assert out[date(2026, 7, 2)] == "tp"
    assert out[date(2026, 8, 1)] == "fp"


def test_m2_recall_counts_each_positive_once():
    a = alerts(("buyer", date(2026, 8, 20)), ("buyer", date(2026, 8, 25)), ("noise", date(2026, 8, 1)))
    s = summarize(a, TRUTH, WIN)
    assert s["recall"] == 0.5
    assert s["alerts"] == 3
    assert s["precision_alerts"] == 2 / 3
    assert s["precision_accounts"] == 0.5


def test_m3_lead_time_uses_first_tp_alert():
    a = alerts(("buyer", date(2026, 8, 1)), ("buyer", date(2026, 8, 25)))
    assert summarize(a, TRUTH, WIN)["median_lead_days"] == 30


def test_alerts_outside_window_ignored_and_weeks_counted():
    a = alerts(("noise", date(2026, 6, 28)), ("noise", date(2026, 6, 29)), ("noise", date(2026, 7, 5)), ("noise", date(2026, 7, 6)))
    assert summarize(a, TRUTH, WIN)["alerts"] == 3
    weeks = weekly_counts(a["alert_date"], WIN)
    assert len(weeks) == 13 and weeks[0] == 2 and weeks[1] == 1
