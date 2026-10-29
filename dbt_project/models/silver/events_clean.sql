-- Scorable engagement and hand-raise events: resolved, bot bursts removed, weighted, capped at one per visitor/type/day.
with resolved as (
    select *
    from {{ ref('int_events_resolved') }}
    where account_id is not null and event_type is not null
),

not_bot as (
    select r.*
    from resolved r
    anti join {{ ref('int_bot_events') }} b on b.event_id = r.event_id
),

weighted as (
    select
        n.*,
        t.category,
        t.funnel_stage,
        t.weight,
        t.half_life_days,
        row_number() over (
            partition by n.observed_key, n.event_type, cast(n.occurred_at as date)
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
    observed_key,
    person_known_at,
    contact_id,
    event_type,
    source,
    occurred_at,
    -- Web events wait one hour: bot classification looks 60 minutes ahead.
    case when source in ('web', 'ads') then greatest(known_at, occurred_at + interval 60 minute) else known_at end as known_at,
    category,
    funnel_stage,
    weight,
    half_life_days,
    resolution_method
from weighted
where rn = 1
