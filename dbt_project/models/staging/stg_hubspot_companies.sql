select
    signal_account_id as account_id,
    hubspot_id,
    lower(lifecyclestage) as lifecyclestage,
    coalesce(open_deals, 0) as open_deals,
    coalesce(do_not_contact, false) as do_not_contact,
    synced_at
from {{ source('bronze', 'hubspot_companies') }}
where signal_account_id is not null
