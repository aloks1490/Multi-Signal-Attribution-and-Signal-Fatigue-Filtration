select account_id, score_date
from {{ ref('account_daily_scores') }}
where engine_score < 0 or activity_score < 0 or trigger_score < 0
