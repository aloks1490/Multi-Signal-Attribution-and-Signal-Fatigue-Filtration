"""Who gets an alert today: entry, cooldown, score-jump override and per-AE budget.

One implementation, used by the dbt Python model (gold.engine_alerts) and by calibration/reporting.
Pure function: arrays in, arrays out, no database.

Rules, applied day by day:
- An account is Hot when its score is at or above the threshold.
- Entry: it becomes Hot today. It is a candidate unless it alerted in the last `cooldown_days` (logged "cooldown").
- Jump: already alerted, at least `jump_min_days` ago, and today's score is at least `jump_ratio` x the score at
  its last alert. A jump breaks the cooldown: a buyer getting much hotter resurfaces.
- Budget: each AE gets at most `ae_daily` alerts a day and `ae_weekly` a Monday-Sunday week. Candidates are ranked
  by score; the rest are deferred and stay in the queue while still Hot, for up to `defer_days` days, then dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

STATUSES = ("alerted", "cooldown", "deferred", "dropped", "expired")


@dataclass(frozen=True)
class AlertRules:
    cooldown_days: int = 14
    jump_ratio: float = 1.5
    jump_min_days: int = 3
    ae_daily: int = 2
    ae_weekly: int = 10
    defer_days: int = 3

    @classmethod
    def from_params(cls, params: dict[str, str]) -> "AlertRules":
        return cls(
            cooldown_days=int(params["cooldown_days"]),
            jump_ratio=float(params["jump_ratio"]),
            jump_min_days=int(params["jump_min_days"]),
            ae_daily=int(params["ae_daily_budget"]),
            ae_weekly=int(params["ae_weekly_budget"]),
            defer_days=int(params["defer_days"]),
        )


def run_alerts(scores: np.ndarray, owners: list[str], days: list[date], threshold: float, rules: AlertRules) -> pd.DataFrame:
    """scores: accounts x consecutive days. Returns one row per logged decision:
    account (row index), day (column index), status, kind (entry / jump / deferred), score."""
    n, n_days = scores.shape
    owner_codes, owner_index = np.unique(np.asarray(owners), return_inverse=True)
    weeks = [d.isocalendar()[:2] for d in days]

    prev_hot = np.zeros(n, dtype=bool)
    last_alert = np.full(n, -10**9)
    last_score = np.zeros(n)
    pending_since = np.full(n, -1)
    used_week = np.zeros(len(owner_codes), dtype=int)
    log: list[tuple[int, int, str, str, float]] = []

    for t in range(n_days):
        if t > 0 and weeks[t] != weeks[t - 1]:
            used_week[:] = 0
        s = scores[:, t]
        hot = s >= threshold
        entry = hot & ~prev_hot
        since = t - last_alert
        has_alert = last_alert > -10**9
        jump = hot & has_alert & (since >= rules.jump_min_days) & (s >= rules.jump_ratio * last_score)
        fresh_entry = entry & (since >= rules.cooldown_days)
        for i in np.nonzero(entry & ~fresh_entry & ~jump)[0]:
            log.append((i, t, "cooldown", "entry", s[i]))

        # The deferral queue: drop accounts that cooled down or waited too long.
        queued = pending_since >= 0
        for i in np.nonzero(queued & ~hot)[0]:
            log.append((i, t, "expired", "deferred", s[i]))
        for i in np.nonzero(queued & hot & (t - pending_since > rules.defer_days))[0]:
            log.append((i, t, "dropped", "deferred", s[i]))
        pending_since[queued & (~hot | (t - pending_since > rules.defer_days))] = -1
        still_queued = pending_since >= 0

        candidates = np.nonzero(fresh_entry | jump | still_queued)[0]
        kinds = {i: ("jump" if jump[i] else "entry" if fresh_entry[i] else "deferred") for i in candidates}

        by_owner: dict[int, list[int]] = {}
        for i in candidates:
            by_owner.setdefault(owner_index[i], []).append(i)
        for o, members in by_owner.items():
            members.sort(key=lambda i: (-s[i], i))  # highest score first; index breaks ties deterministically
            allowance = max(0, min(rules.ae_daily, rules.ae_weekly - used_week[o]))
            for rank, i in enumerate(members):
                if rank < allowance:
                    log.append((i, t, "alerted", kinds[i], s[i]))
                    last_alert[i], last_score[i], pending_since[i] = t, s[i], -1
                    used_week[o] += 1
                else:
                    log.append((i, t, "deferred", kinds[i], s[i]))
                    if pending_since[i] < 0:
                        pending_since[i] = t
        prev_hot = hot

    return pd.DataFrame(log, columns=["account", "day", "status", "kind", "score"])


def alerts_frame(scores: pd.DataFrame, threshold: float, rules: AlertRules) -> pd.DataFrame:
    """Convenience wrapper over a long table (account_id, score_date, engine_score, owner_ae_id)."""
    wide = scores.pivot(index="account_id", columns="score_date", values="engine_score").sort_index(axis=1)
    owners = scores.drop_duplicates("account_id").set_index("account_id").loc[wide.index, "owner_ae_id"].tolist()
    days = [pd.Timestamp(c).date() for c in wide.columns]
    log = run_alerts(wide.to_numpy(), owners, days, threshold, rules)
    ids = np.asarray(wide.index)
    return pd.DataFrame({
        "account_id": ids[log["account"].to_numpy()] if len(log) else [],
        "score_date": [days[d] for d in log["day"]],
        "status": log["status"],
        "kind": log["kind"],
        "engine_score": log["score"],
        "owner_ae_id": [owners[a] for a in log["account"]],
    })
