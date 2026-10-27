select a.account_id
from {{ ref('engine_alerts') }} a
join {{ ref('account_exclusions') }} x on x.account_id = a.account_id
where x.excluded
