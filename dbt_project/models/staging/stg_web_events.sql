select
    event_id,
    cast(occurred_at as timestamp) as occurred_at,
    anonymous_id,
    lower(contact_email) as contact_email,
    ip,
    page_path,
    utm_source
from {{ source('bronze', 'web_events') }}
