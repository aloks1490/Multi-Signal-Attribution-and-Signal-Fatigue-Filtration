-- Alert on entry: an account alerts the first day its score reaches the threshold,
-- and again only after re-crossing at least rearm_days after its previous alert.
-- Wrapped in a subquery so dbt unit tests can inject fixture CTEs in front of it.
select * from (
with recursive
scored as (
    select
        s.account_id,
        s.score_date,
        s.engine_score,
        s.top_signals,
        a.owner_ae_id,
        s.engine_score >= {{ param('engine_threshold') }} as is_hot
    from {{ ref('account_daily_scores') }} s
    join {{ ref('account_exclusions') }} x on x.account_id = s.account_id
    join {{ ref('stg_accounts') }} a on a.account_id = s.account_id
    where not x.excluded
),

flagged as (
    select
        *,
        coalesce(lag(is_hot) over (partition by account_id order by score_date), false) as was_hot
    from scored
),

entries as (
    select
        *,
        row_number() over (partition by account_id order by score_date) as rn
    from flagged
    where is_hot and not was_hot
),

chain(account_id, rn, score_date, last_alert) as (
    select account_id, rn, score_date, score_date
    from entries
    where rn = 1
    union all
    select
        e.account_id,
        e.rn,
        e.score_date,
        case
            when e.score_date >= c.last_alert + {{ param('rearm_days', 'integer') }} then e.score_date
            else c.last_alert
        end
    from chain c
    join entries e on e.account_id = c.account_id and e.rn = c.rn + 1
)

select
    e.account_id,
    e.score_date as alert_date,
    e.owner_ae_id,
    e.engine_score,
    'hot' as tier,
    e.top_signals
from chain c
join entries e on e.account_id = c.account_id and e.rn = c.rn
where c.score_date = c.last_alert
)
