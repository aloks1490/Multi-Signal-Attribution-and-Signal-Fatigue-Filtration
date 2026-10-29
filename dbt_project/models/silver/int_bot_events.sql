-- Web events inside a machine-like burst: any 60-minute window in which one visitor has >= bot_events_per_hour events.
-- A window with enough events can always be slid to start at its first event, so "anchor" events that open such a
-- window find every burst exactly, including bursts that straddle a clock-hour boundary.
-- Classifying an event uses data up to 60 minutes after it; events_clean delays web events' known_at by that hour.
with web as (
    select event_id, observed_key, occurred_at
    from {{ ref('int_events_resolved') }}
    where source in ('web', 'ads')
),

anchors as (
    select observed_key, occurred_at as window_start
    from (
        select
            *,
            count(*) over (
                partition by observed_key order by occurred_at
                range between current row and interval 60 minute following
            ) as n_next_hour
        from web
    )
    where n_next_hour >= {{ param('bot_events_per_hour', 'integer') }}
)

select distinct w.event_id, w.observed_key, w.occurred_at
from web w
join anchors a
    on a.observed_key = w.observed_key
   and w.occurred_at between a.window_start and a.window_start + interval 60 minute
