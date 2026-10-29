-- Static points behave like an MQL: at most one alert per account per profile.
select profile, account_id, count(*) as n
from {{ ref('baseline_points_alerts') }}
group by 1, 2
having count(*) > 1
