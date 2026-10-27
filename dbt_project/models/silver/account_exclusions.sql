-- Accounts that must never alert. One reason per account, in priority order.
with reasons as (
    select
        a.account_id,
        case
            when a.customer_status = 'customer' then 'customer'
            when a.is_competitor then 'competitor'
            when a.has_open_deal then 'open_deal'
            when a.do_not_contact then 'do_not_contact'
            when f.fit_grade = 'D' then 'fit_d'
        end as reason
    from {{ ref('stg_accounts') }} a
    join {{ ref('account_fit') }} f on f.account_id = a.account_id
)

select account_id, reason is not null as excluded, reason
from reasons
