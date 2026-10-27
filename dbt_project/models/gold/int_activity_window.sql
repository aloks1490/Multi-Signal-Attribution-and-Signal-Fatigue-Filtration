-- 14-day activity shape per account and day: people, BOFU people, sources. Used for explanations (M1) and multipliers (M2).
select
    d.score_date,
    e.account_id,
    count(distinct e.person_key) as people_14d,
    count(distinct case when e.funnel_stage = 'BOFU' then e.person_key end) as bofu_people_14d,
    count(distinct e.source) as sources_14d
from {{ ref('date_spine') }} d
join {{ ref('events_clean') }} e
    on e.category = 'engagement'
   and e.weight > 0
   and e.known_at < cast(d.score_date as timestamp)
   and e.occurred_at >= cast(d.score_date as timestamp) - interval 14 day
group by 1, 2
