select e.event_id
from {{ ref('events_clean') }} e
join {{ ref('int_bot_hours') }} b on b.person_key = e.person_key and b.hour = date_trunc('hour', e.occurred_at)
