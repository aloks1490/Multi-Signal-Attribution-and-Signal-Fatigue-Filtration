-- A cookie that ever appears with a known email belongs to that contact, from the first time it did.
select
    w.anonymous_id,
    min_by(c.contact_id, w.occurred_at) as contact_id,
    min(w.occurred_at) as stitched_at
from {{ ref('stg_web_events') }} w
join {{ ref('stg_contacts') }} c on c.email = w.contact_email
where w.anonymous_id is not null
group by w.anonymous_id
