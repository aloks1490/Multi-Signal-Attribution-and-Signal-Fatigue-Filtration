select e.event_id
from {{ ref('events_clean') }} e
join {{ ref('int_bot_events') }} b on b.event_id = e.event_id
