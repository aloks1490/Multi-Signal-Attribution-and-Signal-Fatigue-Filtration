-- Baseline 2: classic lead scoring. Points never decay; an account alerts once (like an MQL),
-- the day after its cumulative points first reach the profile's threshold (precise = dev F1, broad = dev F2).
with points as (
    select account_id, known_at as ts, event_id, weight
    from {{ ref('events_clean') }}
    where category = 'engagement'
    union all
    select account_id, occurred_at, event_id, weight
    from {{ ref('triggers_clean') }}
),

running as (
    select
        *,
        sum(weight) over (partition by account_id order by ts, event_id rows between unbounded preceding and current row) as cum_points
    from points
),

profiles as (
    select 'precise' as profile, {{ param('points_threshold_precise') }} as threshold
    union all
    select 'broad', {{ param('points_threshold_broad') }}
),

crossings as (
    select p.profile, r.account_id, min(r.ts) as crossed_at
    from running r
    cross join profiles p
    where r.cum_points >= p.threshold
    group by 1, 2
)

select
    c.profile,
    c.account_id,
    cast(c.crossed_at as date) + 1 as alert_date,
    a.owner_ae_id
from crossings c
join {{ ref('account_exclusions') }} x on x.account_id = c.account_id
join {{ ref('stg_accounts') }} a on a.account_id = c.account_id
where not x.excluded
