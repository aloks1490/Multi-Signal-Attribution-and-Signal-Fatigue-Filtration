select profile, account_id, alert_date, count(*) as n
from {{ ref('engine_alerts') }}
group by 1, 2, 3
having count(*) > 1
