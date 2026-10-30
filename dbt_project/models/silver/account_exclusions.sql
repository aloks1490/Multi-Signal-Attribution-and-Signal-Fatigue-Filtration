-- Accounts that must never alert. One reason per account, in priority order.
-- crm_* reasons come from HubSpot (stg_hubspot_companies): a rep marking a company as a customer, adding an open deal
-- or ticking do-not-contact stops its alerts on the next run. HubSpot is current state, not history.
with reasons as (
    select
        a.account_id,
        case
            when a.customer_status = 'customer' then 'customer'
            when a.is_competitor then 'competitor'
            when a.has_open_deal then 'open_deal'
            when a.do_not_contact then 'do_not_contact'
            when h.lifecyclestage in ('customer', 'evangelist') then 'crm_customer'
            when h.open_deals > 0 then 'crm_open_deal'
            when h.do_not_contact then 'crm_do_not_contact'
            when f.fit_grade = 'D' then 'fit_d'
        end as reason
    from {{ ref('stg_accounts') }} a
    join {{ ref('account_fit') }} f on f.account_id = a.account_id
    left join {{ ref('stg_hubspot_companies') }} h on h.account_id = a.account_id
)

select account_id, reason is not null as excluded, reason
from reasons
