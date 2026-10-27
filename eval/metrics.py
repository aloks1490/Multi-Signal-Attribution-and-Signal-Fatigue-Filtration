"""Alert outcome labelling and summary metrics. Reads truth labels; nothing in dbt may."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

TP_WINDOW_DAYS = 60
POSITIVE_CLASSES = ("planted_buyer", "random_converter")


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    n_aes: int

    @property
    def n_weeks(self) -> float:
        return ((self.end - self.start).days + 1) / 7


def positives(truth: pd.DataFrame, window: Window) -> pd.DataFrame:
    t = truth[truth["truth_class"].isin(POSITIVE_CLASSES)].copy()
    t["meeting_date"] = pd.to_datetime(t["meeting_date"]).dt.date
    return t[(t["meeting_date"] >= window.start) & (t["meeting_date"] <= window.end)]


def label_alerts(alerts: pd.DataFrame, truth: pd.DataFrame, window: Window) -> pd.DataFrame:
    """Add `outcome` to each alert in the window: tp, fp or post_meeting.

    tp: positive account, meeting_date - 60 <= alert_date <= meeting_date - 1.
    post_meeting: positive account, alert on or after the meeting (production would exclude it via the new deal).
    fp: everything else, including alerts more than 60 days before the meeting.
    """
    a = alerts.copy()
    a["alert_date"] = pd.to_datetime(a["alert_date"]).dt.date
    a = a[(a["alert_date"] >= window.start) & (a["alert_date"] <= window.end)]
    pos = positives(truth, window)[["account_id", "meeting_date"]]
    a = a.merge(pos, on="account_id", how="left")
    lead = (pd.to_datetime(a["meeting_date"]) - pd.to_datetime(a["alert_date"])).dt.days
    a["lead_days"] = lead
    a["outcome"] = "fp"
    a.loc[a["meeting_date"].notna() & (lead >= 1) & (lead <= TP_WINDOW_DAYS), "outcome"] = "tp"
    a.loc[a["meeting_date"].notna() & (lead <= 0), "outcome"] = "post_meeting"
    return a


def summarize(alerts: pd.DataFrame, truth: pd.DataFrame, window: Window) -> dict:
    labelled = label_alerts(alerts, truth, window)
    counted = labelled[labelled["outcome"] != "post_meeting"]
    tp = counted[counted["outcome"] == "tp"]
    pos = positives(truth, window)
    alerted_accounts = counted["account_id"].nunique()
    caught = tp.groupby("account_id")["lead_days"].max()  # first TP alert = largest lead
    n = len(counted)
    return {
        "alerts": n,
        "alerts_per_ae_week": n / window.n_aes / window.n_weeks,
        "precision_alerts": len(tp) / n if n else 0.0,
        "precision_accounts": tp["account_id"].nunique() / alerted_accounts if alerted_accounts else 0.0,
        "recall": len(caught) / len(pos) if len(pos) else 0.0,
        "median_lead_days": float(caught.median()) if len(caught) else None,
        "post_meeting_alerts": int((labelled["outcome"] == "post_meeting").sum()),
        "positives": len(pos),
        "caught_ids": sorted(caught.index),
    }


def weekly_counts(alert_dates: pd.Series, window: Window) -> pd.Series:
    """Alerts per Monday-start week inside the window (weeks with none included as 0)."""
    d = pd.to_datetime(pd.Series(alert_dates)).dt.date
    d = d[(d >= window.start) & (d <= window.end)]
    weeks = d.map(lambda x: (x - window.start).days // 7)
    n_weeks = ((window.end - window.start).days + 1 + 6) // 7
    return weeks.value_counts().reindex(range(n_weeks), fill_value=0).sort_index()
