-- Demo requests skip scoring and go straight to the owner the next morning.
select
    e.account_id,
    cast(e.known_at as date) + 1 as routed_date,
    e.person_key,
    a.owner_ae_id
from {{ ref('events_clean') }} e
join {{ ref('account_exclusions') }} x on x.account_id = e.account_id
join {{ ref('stg_accounts') }} a on a.account_id = e.account_id
where e.category = 'handraise' and not x.excluded
