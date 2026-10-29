-- One row per account per score date.
--   M1: engine_score_m1 = fit × (activity + triggers)
--   M2: engine_score    = fit × (activity × m_breadth × m_sources × m_spike × m_gate + triggers + combo bonuses)
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

combos as (
    select account_id, score_date, sum(bonus) as combo_bonus, string_agg(combo, ' + ' order by bonus desc, combo) as combos
    from {{ ref('int_combo_matches') }}
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
),

scored as (
    select
        g.account_id,
        g.score_date,
        coalesce(a.activity_score, 0) as activity_score,
        coalesce(t.trigger_score, 0) as trigger_score,
        coalesce(c.combo_bonus, 0) as combo_bonus,
        g.fit_grade,
        g.fit_multiplier,
        coalesce(p.people_14d, 0) as people_14d,
        coalesce(p.bofu_people_14d, 0) as bofu_people_14d,
        coalesce(p.sources_14d, 0) as sources_14d,
        coalesce(p.spike_ratio, 0) as spike_ratio,
        coalesce(p.m_breadth, 1.0) as m_breadth,
        coalesce(p.m_sources, 1.0) as m_sources,
        coalesce(p.m_spike, 1.0) as m_spike,
        -- No recent engagement at all means no BOFU either, so the gate applies.
        coalesce(p.m_gate, {{ param('no_bofu_multiplier') }}) as m_gate,
        c.combos,
        ts.top_signals
    from grid g
    left join activity a on a.account_id = g.account_id and a.score_date = g.score_date
    left join triggers t on t.account_id = g.account_id and t.score_date = g.score_date
    left join combos c on c.account_id = g.account_id and c.score_date = g.score_date
    left join {{ ref('int_pattern_metrics') }} p on p.account_id = g.account_id and p.score_date = g.score_date
    left join top_signals ts on ts.account_id = g.account_id and ts.score_date = g.score_date
),

final as (
    select
        *,
        fit_multiplier * (activity_score + trigger_score) as engine_score_m1,
        fit_multiplier * (activity_score * m_breadth * m_sources * m_spike * m_gate + trigger_score + combo_bonus) as engine_score
    from scored
)

select
    *,
    -- One line a rep can act on, e.g. "62 · fit A · 3 people · pricing_page, comparison_page, new_sales_leader · 4.2× usual activity · evaluation + team_trial"
    concat_ws(' · ',
        cast(round(engine_score) as integer)::varchar,
        'fit ' || fit_grade,
        case when people_14d = 1 then '1 person' when people_14d > 1 then people_14d || ' people' end,
        top_signals,
        case when spike_ratio >= 2 then round(spike_ratio, 1) || '× usual activity' end,
        combos
    ) as reason
from final
