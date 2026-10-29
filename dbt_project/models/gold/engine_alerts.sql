-- Alerts that reached reps' queues, for both threshold profiles (precise = best dev F1, broad = best dev F2).
-- Cooldown, score-jump override and the per-AE budget are decided in alert_candidates (engine/alerting.py).
-- is_active marks the team-level profile (scoring_params.active_profile) that activation sends to reps.
select
    c.profile,
    c.profile = {{ param('active_profile', 'varchar') }} as is_active,
    c.account_id,
    c.score_date as alert_date,
    c.owner_ae_id,
    c.engine_score,
    'hot' as tier,
    c.kind as alert_kind,
    s.top_signals,
    s.reason
from {{ ref('alert_candidates') }} c
join {{ ref('account_daily_scores') }} s
    on s.account_id = c.account_id and s.score_date = c.score_date
where c.status = 'alerted'
