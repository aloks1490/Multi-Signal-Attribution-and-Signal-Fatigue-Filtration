-- Scorable engagement and hand-raise events: resolved, bot hours removed, weighted, capped at one per person/type/day.
with resolved as (
    select *
    from {{ ref('int_events_resolved') }}
    where account_id is not null and event_type is not null
),

not_bot as (
    select r.*
    from resolved r
    left join {{ ref('int_bot_hours') }} b
        on b.person_key = r.person_key and b.hour = date_trunc('hour', r.occurred_at)
    where b.person_key is null
),

weighted as (
    select
        n.*,
        t.category,
        t.funnel_stage,
        t.weight,
        t.half_life_days,
        row_number() over (
            partition by n.person_key, n.event_type, cast(n.occurred_at as date)
            order by n.occurred_at, n.event_id
        ) as rn
    from not_bot n
    join {{ ref('signal_taxonomy') }} t
        on t.event_type = n.event_type and t.category in ('engagement', 'handraise')
)

select
    event_id,
    account_id,
    person_key,
    contact_id,
    event_type,
    source,
    occurred_at,
    known_at,
    category,
    funnel_stage,
    weight,
    half_life_days,
    resolution_method
from weighted
where rn = 1
