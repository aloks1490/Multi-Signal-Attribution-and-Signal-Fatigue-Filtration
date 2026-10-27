-- External triggers (funding, hires, job posts, tool changes) tied to accounts by domain.
select
    t.event_id,
    a.account_id,
    t.trigger_type,
    t.occurred_at,
    t.closed_at,
    t.detail,
    x.weight,
    x.half_life_days
from {{ ref('stg_trigger_events') }} t
join {{ ref('stg_accounts') }} a on a.domain = t.account_domain
join {{ ref('signal_taxonomy') }} x on x.event_type = t.trigger_type and x.category = 'trigger'
