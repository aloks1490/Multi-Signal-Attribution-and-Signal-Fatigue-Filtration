-- Fact sheet for each alert: the only facts an LLM may use to explain it (activation/narrate.py checks this).
with alerts as (
    select distinct account_id, alert_date from {{ ref('engine_alerts') }}
),

people as (
    -- Known contacts active in the 14 days before the alert, with what each of them did.
    select
        a.account_id,
        a.alert_date,
        e.contact_id,
        any_value(c.first_name || ' ' || c.last_name) as name,
        any_value(c.first_name) as first_name,
        any_value(c.last_name) as last_name,
        any_value(c.email) as email,
        any_value(c.title) as title,
        any_value(c.seniority) as seniority,
        any_value(c.function) as function,
        list(distinct e.event_type order by e.event_type) as did,
        max(e.occurred_at) as last_seen
    from alerts a
    join {{ ref('events_clean') }} e
        on e.account_id = a.account_id
       and e.known_at < cast(a.alert_date as timestamp)
       and e.occurred_at >= cast(a.alert_date as timestamp) - interval 14 day
       and e.category = 'engagement' and e.weight > 0
    join {{ ref('stg_contacts') }} c on c.contact_id = e.contact_id
    group by 1, 2, 3
),

anonymous as (
    select a.account_id, a.alert_date, count(distinct e.person_key) as anonymous_visitors
    from alerts a
    join {{ ref('events_clean') }} e
        on e.account_id = a.account_id
       and e.known_at < cast(a.alert_date as timestamp)
       and e.occurred_at >= cast(a.alert_date as timestamp) - interval 14 day
       and e.contact_id is null
    group by 1, 2
),

signals as (
    select a.account_id, a.alert_date, e.event_type, e.funnel_stage, count(*) as n
    from alerts a
    join {{ ref('events_clean') }} e
        on e.account_id = a.account_id
       and e.known_at < cast(a.alert_date as timestamp)
       and e.occurred_at >= cast(a.alert_date as timestamp) - interval 14 day
       and e.weight > 0
    group by 1, 2, 3, 4
),

triggers as (
    select a.account_id, a.alert_date, t.trigger_type, t.detail, cast(t.occurred_at as date) as on_date
    from alerts a
    join {{ ref('triggers_clean') }} t
        on t.account_id = a.account_id
       and t.occurred_at < cast(a.alert_date as timestamp)
       and t.occurred_at >= cast(a.alert_date as timestamp) - interval 90 day
)

select
    a.account_id,
    a.alert_date,
    c.company_name,
    c.domain,
    c.industry,
    c.employee_count,
    c.region,
    c.crm,
    c.owner_ae_id,
    f.fit_grade,
    f.fit_points,
    s.engine_score,
    s.people_14d,
    s.sources_14d,
    s.spike_ratio,
    s.combos,
    s.top_signals,
    s.reason,
    coalesce(an.anonymous_visitors, 0) as anonymous_visitors,
    (select list(struct_pack(contact_id := p.contact_id, name := p.name, first_name := p.first_name, last_name := p.last_name,
                             email := p.email, title := p.title, seniority := p.seniority, function := p.function,
                             did := p.did, last_seen := cast(p.last_seen as date)) order by p.last_seen desc)
     from people p where p.account_id = a.account_id and p.alert_date = a.alert_date) as people,
    (select list(struct_pack(signal := g.event_type, stage := g.funnel_stage, n := g.n) order by g.n desc, g.event_type)
     from signals g where g.account_id = a.account_id and g.alert_date = a.alert_date) as signal_counts,
    (select list(struct_pack(trigger := t.trigger_type, detail := t.detail, on_date := t.on_date) order by t.on_date desc)
     from triggers t where t.account_id = a.account_id and t.alert_date = a.alert_date) as triggers
from alerts a
join {{ ref('stg_accounts') }} c on c.account_id = a.account_id
join {{ ref('account_fit') }} f on f.account_id = a.account_id
join {{ ref('account_daily_scores') }} s on s.account_id = a.account_id and s.score_date = a.alert_date
left join anonymous an on an.account_id = a.account_id and an.alert_date = a.alert_date
