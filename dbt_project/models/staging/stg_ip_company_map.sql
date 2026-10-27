select ip, lower(domain) as domain
from {{ source('bronze', 'ip_company_map') }}
