-- Decayed contribution of triggers. Job posts do not decay while open; decay starts when they close.
-- At most max_open_job_posts posts count per account per day (the largest contributions).
with pairs as (
    select
        d.score_date,
        t.account_id,
        t.trigger_type,
        t.event_id,
        t.weight,
        t.half_life_days,
        case
            when t.trigger_type = 'sdr_job_post'
                 and (t.closed_at is null or t.closed_at >= cast(d.score_date as timestamp)) then 0.0
            when t.trigger_type = 'sdr_job_post' then {{ age_days('d.score_date', 't.closed_at') }}
            else {{ age_days('d.score_date', 't.occurred_at') }}
        end as age
    from {{ ref('date_spine') }} d
    join {{ ref('triggers_clean') }} t
        on t.occurred_at < cast(d.score_date as timestamp)
       and t.occurred_at >= cast(d.score_date as timestamp) - to_days({{ param('lookback_days', 'integer') }})
),

ranked as (
    select
        *,
        {{ decay('weight', 'half_life_days', 'age') }} as contribution,
        row_number() over (
            partition by account_id, score_date, trigger_type
            order by {{ decay('weight', 'half_life_days', 'age') }} desc, event_id
        ) as rn
    from pairs
)

select
    account_id,
    score_date,
    trigger_type,
    sum(contribution) as contribution,
    count(*) as n_events
from ranked
where trigger_type <> 'sdr_job_post' or rn <= {{ param('max_open_job_posts', 'integer') }}
group by 1, 2, 3
