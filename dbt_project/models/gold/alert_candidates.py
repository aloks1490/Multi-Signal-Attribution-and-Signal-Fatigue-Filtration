"""Every alerting decision, per threshold profile: alerted, cooldown, deferred, dropped or expired.

The rules live in engine/alerting.py (one implementation shared with calibration and reporting).
"""
import pandas as pd

from engine.alerting import AlertRules, alerts_frame


def model(dbt, session):
    dbt.config(materialized="table")
    # Each dbt.ref must be a plain statement: dbt finds dependencies by parsing these calls.
    params_df = dbt.ref("scoring_params").df()
    params = dict(params_df[["param", "value"]].values)
    scores = dbt.ref("account_daily_scores").df()[["account_id", "score_date", "engine_score"]]
    excluded = dbt.ref("account_exclusions").df()
    owners = dbt.ref("stg_accounts").df()[["account_id", "owner_ae_id"]]

    keep = excluded.loc[~excluded["excluded"].astype(bool), "account_id"]
    scores = scores[scores["account_id"].isin(keep)].merge(owners, on="account_id")
    rules = AlertRules.from_params(params)

    frames = []
    for profile in ("precise", "broad"):
        out = alerts_frame(scores, float(params[f"engine_threshold_{profile}"]), rules)
        out.insert(0, "profile", profile)
        frames.append(out)
    result = pd.concat(frames, ignore_index=True)
    result["score_date"] = pd.to_datetime(result["score_date"]).dt.date
    return result
