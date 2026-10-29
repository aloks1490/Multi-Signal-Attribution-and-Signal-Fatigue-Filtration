-- No AE gets more alerts than the daily or weekly budget, in either profile.
with daily as (
    select profile, owner_ae_id, alert_date, count(*) as n
    from {{ ref('engine_alerts') }}
    group by 1, 2, 3
),
weekly as (
    select profile, owner_ae_id, date_trunc('week', alert_date) as week, count(*) as n
    from {{ ref('engine_alerts') }}
    group by 1, 2, 3
)
select 'daily' as cap, profile, owner_ae_id, n from daily where n > {{ param('ae_daily_budget', 'integer') }}
union all
select 'weekly', profile, owner_ae_id, n from weekly where n > {{ param('ae_weekly_budget', 'integer') }}
