-- Events that cannot be used: no account match or an unmapped page. Kept for monitoring match rates.
select
    event_id,
    source,
    occurred_at,
    case when account_id is null then 'no_account' else 'unmapped_type' end as reason
from {{ ref('int_events_resolved') }}
where account_id is null or event_type is null
