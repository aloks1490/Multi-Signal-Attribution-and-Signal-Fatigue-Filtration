-- Score dates: a warm-up period before the evaluation window (so alert state is known on day one), then the window.
with bounds as (
    select
        {{ param('eval_start', 'date') }} - {{ param('warmup_days', 'integer') }} as start_date,
        {{ param('eval_end', 'date') }} as end_date
)

select cast(unnest(generate_series(cast(start_date as timestamp), cast(end_date as timestamp), interval 1 day)) as date) as score_date
from bounds
