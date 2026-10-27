select account_id, score_date
from {{ ref('account_daily_scores') }}
where fit_grade = 'D' and engine_score <> 0
