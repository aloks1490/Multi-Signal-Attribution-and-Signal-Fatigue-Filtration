select
    event_id,
    cast(occurred_at as timestamp) as occurred_at,
    cast(closed_at as timestamp) as closed_at,
    lower(account_domain) as account_domain,
    trigger_type,
    detail
from {{ source('bronze', 'trigger_events') }}
