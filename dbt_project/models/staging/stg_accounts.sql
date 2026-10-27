select
    account_id,
    company_name,
    lower(domain) as domain,
    industry,
    cast(employee_count as integer) as employee_count,
    cast(sales_headcount as integer) as sales_headcount,
    region,
    crm,
    tech_stack,
    customer_status,
    cast(is_competitor as boolean) as is_competitor,
    cast(has_open_deal as boolean) as has_open_deal,
    cast(do_not_contact as boolean) as do_not_contact,
    owner_ae_id
from {{ source('bronze', 'accounts') }}
