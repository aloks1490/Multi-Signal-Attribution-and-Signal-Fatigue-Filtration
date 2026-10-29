-- Named signal combinations that mean intent, per account and score date (M2). One row per matched combo.
with rules as (
    select * from {{ ref('combo_rules') }}
),

events as (
    select *
    from {{ ref('events_clean') }}
    where category = 'engagement' and weight > 0
),

recent as (
    -- Engagement in the engagement combos' window (14 days), with the person as known on the score date.
    select
        d.score_date,
        e.account_id,
        e.event_type,
        e.funnel_stage,
        e.occurred_at,
        case when e.person_known_at < cast(d.score_date as timestamp) then e.person_key else e.observed_key end as person
    from {{ ref('date_spine') }} d
    join events e
        on e.known_at < cast(d.score_date as timestamp)
       and e.occurred_at >= cast(d.score_date as timestamp) - to_days((select max(window_days) from rules where combo in ('evaluation', 'team_trial')))
),

engagement as (
    select
        score_date,
        account_id,
        count(distinct case when event_type in ('pricing_page', 'comparison_page', 'integration_page', 'security_page') then person end) as eval_people,
        bool_or(event_type in ('pricing_page', 'comparison_page')) as has_price_or_compare,
        bool_or(event_type in ('integration_page', 'security_page')) as has_integration_or_security,
        bool_or(event_type = 'trial_started') as has_trial,
        bool_or(event_type = 'teammate_invited') as has_invite,
        bool_or(funnel_stage in ('MOFU', 'BOFU')) as has_mofu_bofu,
        max(case when funnel_stage = 'BOFU' then occurred_at end) as last_bofu_at
    from recent
    group by 1, 2
),

triggers as (
    -- Triggers in the last 60 days (the trigger combos' window).
    select
        d.score_date,
        t.account_id,
        bool_or(t.trigger_type = 'new_sales_leader') as has_leader,
        bool_or(t.trigger_type = 'sdr_job_post') as has_sdr_posts,
        min(t.occurred_at) as first_trigger_at
    from {{ ref('date_spine') }} d
    join {{ ref('triggers_clean') }} t
        on t.occurred_at < cast(d.score_date as timestamp)
       and t.occurred_at >= cast(d.score_date as timestamp) - to_days((select max(window_days) from rules where combo in ('sales_build', 'trigger_then_intent')))
    group by 1, 2
),

matches as (
    select score_date, account_id, 'evaluation' as combo
    from engagement
    where has_price_or_compare and has_integration_or_security and eval_people >= 2
    union all
    select score_date, account_id, 'team_trial'
    from engagement
    where has_trial and has_invite
    union all
    select e.score_date, e.account_id, 'sales_build'
    from engagement e
    join triggers t using (score_date, account_id)
    where t.has_leader and t.has_sdr_posts and e.has_mofu_bofu
    union all
    select e.score_date, e.account_id, 'trigger_then_intent'
    from engagement e
    join triggers t using (score_date, account_id)
    where e.last_bofu_at > t.first_trigger_at
)

select m.account_id, m.score_date, m.combo, r.bonus
from matches m
join rules r on r.combo = m.combo
