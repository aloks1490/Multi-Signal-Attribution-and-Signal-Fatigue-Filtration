-- Alert on entry, for both threshold profiles: an account alerts the first day its score reaches the profile's
-- threshold, and again only after re-crossing at least rearm_days after its previous alert.
--   precise = best dev F1 (fewer, surer alerts); broad = best dev F2 (catches more buyers).
-- is_active marks the team-level profile (scoring_params.active_profile) that activation sends to reps.
-- Wrapped in a subquery so dbt unit tests can inject fixture CTEs in front of it.
select * from (
with recursive
profiles as (
    select 'precise' as profile, {{ param('engine_threshold_precise') }} as threshold
    union all
    select 'broad', {{ param('engine_threshold_broad') }}
),

scored as (
    select
        p.profile,
        s.account_id,
        s.score_date,
        s.engine_score,
        s.top_signals,
        s.reason,
        a.owner_ae_id,
        s.engine_score >= p.threshold as is_hot
    from {{ ref('account_daily_scores') }} s
    join {{ ref('account_exclusions') }} x on x.account_id = s.account_id
    join {{ ref('stg_accounts') }} a on a.account_id = s.account_id
    cross join profiles p
    where not x.excluded
),

flagged as (
    select
        *,
        coalesce(lag(is_hot) over (partition by profile, account_id order by score_date), false) as was_hot
    from scored
),

entries as (
    select
        *,
        row_number() over (partition by profile, account_id order by score_date) as rn
    from flagged
    where is_hot and not was_hot
),

chain(profile, account_id, rn, score_date, last_alert) as (
    select profile, account_id, rn, score_date, score_date
    from entries
    where rn = 1
    union all
    select
        e.profile,
        e.account_id,
        e.rn,
        e.score_date,
        case
            when e.score_date >= c.last_alert + {{ param('rearm_days', 'integer') }} then e.score_date
            else c.last_alert
        end
    from chain c
    join entries e on e.profile = c.profile and e.account_id = c.account_id and e.rn = c.rn + 1
)

select
    e.profile,
    e.profile = {{ param('active_profile', 'varchar') }} as is_active,
    e.account_id,
    e.score_date as alert_date,
    e.owner_ae_id,
    e.engine_score,
    'hot' as tier,
    e.top_signals,
    e.reason
from chain c
join entries e on e.profile = c.profile and e.account_id = c.account_id and e.rn = c.rn
where c.score_date = c.last_alert
)
