-- Map page paths to taxonomy event types. Paid-traffic hits are ad clicks whatever the page.
with web as (
    select * from {{ ref('stg_web_events') }}
),

matched as (
    select
        w.event_id,
        r.event_type,
        row_number() over (partition by w.event_id order by r.priority, r.path_pattern) as rn
    from web w
    join {{ ref('page_rules') }} r on w.page_path like r.path_pattern
)

select
    w.*,
    case when w.utm_source = 'paid' then 'ad_click' else m.event_type end as event_type
from web w
left join matched m on m.event_id = w.event_id and m.rn = 1
