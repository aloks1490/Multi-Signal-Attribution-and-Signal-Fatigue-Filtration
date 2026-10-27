select
    contact_id,
    account_id,
    lower(email) as email,
    first_name,
    last_name,
    title,
    seniority,
    function
from {{ source('bronze', 'contacts') }}
