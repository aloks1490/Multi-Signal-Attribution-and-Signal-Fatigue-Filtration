-- Baseline 1: every high-intent event at a non-excluded account pings the owner.
-- Uses the same cleaned events as the engine (bots removed, one per person/type/day), which flatters this baseline.
select
    e.event_id,
    e.account_id,
    cast(e.known_at as date) as alert_date,
    e.event_type,
    a.owner_ae_id
from {{ ref('events_clean') }} e
join {{ ref('signal_taxonomy') }} t on t.event_type = e.event_type
join {{ ref('account_exclusions') }} x on x.account_id = e.account_id
join {{ ref('stg_accounts') }} a on a.account_id = e.account_id
where t.baseline_ping and not x.excluded
