-- Decayed contribution of engagement events per account, score date and event type.
-- Point-in-time: a score for day d only sees events known before midnight starting d.
with events as (
    select * from {{ ref('events_clean') }}
    where category = 'engagement'
),

pairs as (
    select
        d.score_date,
        e.account_id,
        e.event_type,
        {{ decay('e.weight', 'e.half_life_days', age_days('d.score_date', 'e.occurred_at')) }} as contribution
    from {{ ref('date_spine') }} d
    join events e
        on e.known_at < cast(d.score_date as timestamp)
       and e.occurred_at >= cast(d.score_date as timestamp) - to_days({{ param('lookback_days', 'integer') }})
)

select
    account_id,
    score_date,
    event_type,
    sum(contribution) as contribution,
    count(*) as n_events
from pairs
group by 1, 2, 3
