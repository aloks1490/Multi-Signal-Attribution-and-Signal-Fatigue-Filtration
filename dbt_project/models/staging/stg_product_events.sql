select
    event_id,
    cast(occurred_at as timestamp) as occurred_at,
    lower(user_email) as user_email,
    event_name
from {{ source('bronze', 'product_events') }}
