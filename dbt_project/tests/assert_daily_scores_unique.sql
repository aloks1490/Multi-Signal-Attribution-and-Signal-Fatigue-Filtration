-- One row per account per score date.
select account_id, score_date, count(*) as n
from {{ ref('account_daily_scores') }}
group by 1, 2
having count(*) > 1
