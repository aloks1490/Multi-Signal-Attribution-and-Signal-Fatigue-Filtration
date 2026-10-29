select a.account_id, a.alert_date
from {{ ref('engine_alerts') }} a
left join {{ ref('alert_context') }} c using (account_id, alert_date)
where c.account_id is null
