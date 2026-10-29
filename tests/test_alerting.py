"""M4: the alerting rules (entry, cooldown, jump, per-AE budget, deferral) on hand-made score series."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from engine.alerting import AlertRules, run_alerts

START = date(2026, 6, 1)  # a Monday
NO_BUDGET = AlertRules(ae_daily=99, ae_weekly=99)


def days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def alerted(log, account: int = 0) -> list[int]:
    return log[(log.status == "alerted") & (log.account == account)].day.tolist()


def series(values: list[float]) -> np.ndarray:
    return np.array([values], dtype=float)


def test_entry_alerts_once_while_hot():
    log = run_alerts(series([5, 20, 20, 20, 5]), ["ae_1"], days(5), 10, NO_BUDGET)
    assert alerted(log) == [1]


def test_cooldown_blocks_reentry_then_rearms():
    s = [5, 20, 5, 20] + [5] * 12 + [20]  # re-enters on day 3 (2 days later) and day 16 (15 days later)
    log = run_alerts(series(s), ["ae_1"], days(len(s)), 10, NO_BUDGET)
    assert alerted(log) == [1, 16]
    assert log[(log.status == "cooldown")].day.tolist() == [3]


def test_score_jump_breaks_cooldown_after_min_days():
    s = [20, 22, 31, 25, 25, 31]  # 31 >= 1.5 x 20, but on day 2 only 2 days have passed; day 5 qualifies
    log = run_alerts(series(s), ["ae_1"], days(len(s)), 10, NO_BUDGET)
    assert alerted(log) == [0, 5]
    assert log[(log.status == "alerted")].kind.tolist() == ["entry", "jump"]


def test_daily_budget_defers_lowest_score_to_next_day():
    s = np.array([[50, 50], [40, 40], [30, 30]], dtype=float)
    log = run_alerts(s, ["ae_1"] * 3, days(2), 10, AlertRules(ae_daily=2, ae_weekly=10))
    assert sorted(log[(log.day == 0) & (log.status == "alerted")].account) == [0, 1]
    assert log[(log.day == 0) & (log.status == "deferred")].account.tolist() == [2]
    assert alerted(log, 2) == [1]
    assert log[(log.account == 2) & (log.status == "alerted")].kind.tolist() == ["deferred"]


def test_budget_is_per_ae():
    s = np.array([[50], [40], [30]], dtype=float)
    log = run_alerts(s, ["ae_1", "ae_1", "ae_2"], days(1), 10, AlertRules(ae_daily=1, ae_weekly=10))
    assert sorted(log[log.status == "alerted"].account) == [0, 2]


def test_deferred_too_long_is_dropped_and_cooled_is_expired():
    rules = AlertRules(ae_daily=1, ae_weekly=99, defer_days=3)
    # Account 0 enters every day with a high score is impossible (entry happens once), so keep the AE busy with new
    # high entries each day: accounts 1..5 enter on days 0..4. Account 0 (lowest) keeps getting deferred.
    s = np.full((6, 6), 0.0)
    s[0, :] = 15
    for k in range(1, 6):
        s[k, k - 1:] = 100 - k
    log = run_alerts(s, ["ae_1"] * 6, days(6), 10, rules)
    acc0 = log[log.account == 0]
    assert acc0.status.tolist() == ["deferred", "deferred", "deferred", "deferred", "dropped"]

    cooled = np.array([[50, 0, 0], [40, 0, 0]], dtype=float)
    log2 = run_alerts(cooled, ["ae_1"] * 2, days(3), 10, rules)
    assert log2[(log2.account == 1)].status.tolist() == ["deferred", "expired"]


def test_weekly_budget_resets_on_monday():
    n = 12
    s = np.zeros((n, 8))
    for k in range(n):
        s[k, :] = 100 - k  # all Hot from day 0
    rules = AlertRules(ae_daily=2, ae_weekly=3, defer_days=99)
    log = run_alerts(s, ["ae_1"] * n, days(8), 10, rules)  # days 0-6 = week 1, day 7 = next Monday
    per_day = log[log.status == "alerted"].groupby("day").size()
    assert per_day.loc[0:6].sum() == 3
    assert per_day.loc[7] == 2


def test_same_alerts_whatever_the_account_order():
    rng = np.random.default_rng(0)
    s = rng.uniform(0, 40, size=(30, 40))
    owners = [f"ae_{i % 3}" for i in range(30)]
    rules = AlertRules(ae_daily=1, ae_weekly=4)
    base = run_alerts(s, owners, days(40), 20, rules)
    perm = rng.permutation(30)
    shuffled = run_alerts(s[perm], [owners[i] for i in perm], days(40), 20, rules)
    shuffled["account"] = perm[shuffled["account"]]
    key = lambda df: sorted(map(tuple, df[df.status == "alerted"][["account", "day"]].values.tolist()))
    assert key(base) == key(shuffled)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_matches_m1_rule_when_budget_and_jump_are_off(seed):
    """With no budget and no jump, the rules reduce to M1's alert-on-entry with a 14-day re-arm."""
    from eval.calibrate import simulate_entry_alerts

    rng = np.random.default_rng(seed)
    s = rng.uniform(0, 40, size=(50, 60))
    rules = AlertRules(cooldown_days=14, jump_ratio=1e9, ae_daily=999, ae_weekly=999)
    log = run_alerts(s, ["ae_1"] * 50, days(60), 20, rules)
    old = simulate_entry_alerts(s, 20, 14)
    new = np.zeros_like(old)
    hit = log[log.status == "alerted"]
    new[hit.account, hit.day] = True
    assert (old == new).all()
