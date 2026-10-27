-- Person-hours with machine-like volume. Only those hours are dropped, so the rule never uses future data.
select
    person_key,
    date_trunc('hour', occurred_at) as hour,
    count(*) as events
from {{ ref('int_events_resolved') }}
where source in ('web', 'ads')
group by 1, 2
having count(*) >= {{ param('bot_events_per_hour', 'integer') }}
