-- One row per account per score date. M1 engine score = fit multiplier × (activity + triggers).
with grid as (
    select f.account_id, f.fit_grade, f.fit_multiplier, d.score_date
    from {{ ref('account_fit') }} f
    cross join {{ ref('date_spine') }} d
),

activity as (
    select account_id, score_date, sum(contribution) as activity_score
    from {{ ref('int_engagement_contrib') }}
    group by 1, 2
),

triggers as (
    select account_id, score_date, sum(contribution) as trigger_score
    from {{ ref('int_trigger_contrib') }}
    group by 1, 2
),

signals as (
    select account_id, score_date, event_type as signal, contribution from {{ ref('int_engagement_contrib') }}
    union all
    select account_id, score_date, trigger_type, contribution from {{ ref('int_trigger_contrib') }}
),

top_signals as (
    select account_id, score_date, string_agg(signal, ', ' order by contribution desc, signal) as top_signals
    from (
        select *, row_number() over (partition by account_id, score_date order by contribution desc, signal) as rn
        from signals
        where contribution >= 0.5
    )
    where rn <= 3
    group by 1, 2
)

select
    g.account_id,
    g.score_date,
    coalesce(a.activity_score, 0) as activity_score,
    coalesce(t.trigger_score, 0) as trigger_score,
    g.fit_grade,
    g.fit_multiplier,
    g.fit_multiplier * (coalesce(a.activity_score, 0) + coalesce(t.trigger_score, 0)) as engine_score,
    coalesce(w.people_14d, 0) as people_14d,
    coalesce(w.bofu_people_14d, 0) as bofu_people_14d,
    coalesce(w.sources_14d, 0) as sources_14d,
    ts.top_signals
from grid g
left join activity a on a.account_id = g.account_id and a.score_date = g.score_date
left join triggers t on t.account_id = g.account_id and t.score_date = g.score_date
left join {{ ref('int_activity_window') }} w on w.account_id = g.account_id and w.score_date = g.score_date
left join top_signals ts on ts.account_id = g.account_id and ts.score_date = g.score_date
