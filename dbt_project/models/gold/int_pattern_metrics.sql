-- Shape of each account's recent engagement, per score date, and the activity multipliers it earns (M2).
-- People are counted as the warehouse knew them on that date: a cookie stitched to a contact later still counts
-- as an anonymous visitor before the stitch.
with events as (
    select *
    from {{ ref('events_clean') }}
    where category = 'engagement' and weight > 0
),

pairs as (
    select
        d.score_date,
        e.account_id,
        e.source,
        e.funnel_stage,
        e.occurred_at,
        case when e.person_known_at < cast(d.score_date as timestamp) then e.person_key else e.observed_key end as person
    from {{ ref('date_spine') }} d
    join events e
        on e.known_at < cast(d.score_date as timestamp)
       and e.occurred_at >= cast(d.score_date as timestamp) - interval 63 day
),

shape as (
    select
        score_date,
        account_id,
        count(distinct case when occurred_at >= cast(score_date as timestamp) - interval 14 day
                             and funnel_stage in ('MOFU', 'BOFU') then person end) as people_14d,
        count(distinct case when occurred_at >= cast(score_date as timestamp) - interval 14 day
                             and funnel_stage = 'BOFU' then person end) as bofu_people_14d,
        count(distinct case when occurred_at >= cast(score_date as timestamp) - interval 14 day then source end) as sources_14d,
        count(case when occurred_at >= cast(score_date as timestamp) - interval 7 day then 1 end) as events_7d,
        count(case when occurred_at < cast(score_date as timestamp) - interval 7 day then 1 end) as events_prior_8w
    from pairs
    group by 1, 2
),

ratios as (
    select
        *,
        bofu_people_14d > 0 as has_bofu_14d,
        events_7d / greatest(events_prior_8w / 8.0, 1.0) as spike_ratio
    from shape
),

mult as (
    select * from {{ ref('pattern_multipliers') }}
)

select
    r.*,
    case when r.has_bofu_14d then b.value else 1.0 end as m_breadth,
    case when r.has_bofu_14d then s.value else 1.0 end as m_sources,
    case when r.has_bofu_14d and r.people_14d >= {{ param('spike_min_people', 'integer') }} then k.value else 1.0 end as m_spike,
    case when r.has_bofu_14d then 1.0 else {{ param('no_bofu_multiplier') }} end as m_gate
from ratios r
left join mult b on b.multiplier = 'breadth' and r.people_14d >= b.min_value and r.people_14d < b.max_value
left join mult s on s.multiplier = 'sources' and r.sources_14d >= s.min_value and r.sources_14d < s.max_value
left join mult k on k.multiplier = 'spike' and r.spike_ratio >= k.min_value and r.spike_ratio < k.max_value
