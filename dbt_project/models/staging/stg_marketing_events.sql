select
    event_id,
    cast(occurred_at as timestamp) as occurred_at,
    lower(contact_email) as contact_email,
    event_name,
    campaign_id
from {{ source('bronze', 'marketing_events') }}
