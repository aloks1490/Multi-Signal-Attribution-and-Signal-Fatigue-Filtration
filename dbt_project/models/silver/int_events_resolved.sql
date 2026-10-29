-- Every first-party event tied to an account and a person where possible.
-- known_at        = when the warehouse could first attribute the event to its account (later than occurred_at only for cookie stitching).
-- observed_key    = the identity visible on the event itself (contact for emails, anon:<cookie> otherwise). Never uses later data.
-- person_key      = best identity once all stitching is known; usable for a score date only after person_known_at.
with contacts as (
    select * from {{ ref('stg_contacts') }}
),

accounts as (
    select * from {{ ref('stg_accounts') }}
),

web as (
    select
        w.event_id,
        w.occurred_at,
        w.event_type,
        case when w.event_type = 'ad_click' then 'ads' else 'web' end as source,
        w.anonymous_id,
        ce.contact_id as email_contact_id,
        ce.account_id as email_account_id,
        st.contact_id as stitched_contact_id,
        cs.account_id as stitched_account_id,
        st.stitched_at,
        ip_acc.account_id as ip_account_id
    from {{ ref('int_web_events_mapped') }} w
    left join contacts ce on ce.email = w.contact_email
    left join {{ ref('int_cookie_stitch') }} st on st.anonymous_id = w.anonymous_id
    left join contacts cs on cs.contact_id = st.contact_id
    left join {{ ref('stg_ip_company_map') }} ipm on ipm.ip = w.ip
    left join accounts ip_acc on ip_acc.domain = ipm.domain
),

web_resolved as (
    select
        event_id,
        occurred_at,
        case
            when email_contact_id is not null or ip_account_id is not null then occurred_at
            when stitched_contact_id is not null then greatest(occurred_at, stitched_at)
        end as known_at,
        event_type,
        source,
        coalesce(email_contact_id, stitched_contact_id) as contact_id,
        coalesce(email_account_id, ip_account_id, stitched_account_id) as account_id,
        coalesce(email_contact_id, stitched_contact_id, 'anon:' || anonymous_id) as person_key,
        coalesce(email_contact_id, 'anon:' || anonymous_id) as observed_key,
        case
            when stitched_contact_id is not null and email_contact_id is null then greatest(occurred_at, stitched_at)
            else occurred_at
        end as person_known_at,
        case
            when email_contact_id is not null then 'email'
            when ip_account_id is not null then 'ip'
            when stitched_contact_id is not null then 'cookie_stitch'
        end as resolution_method
    from web
),

email_events as (
    select event_id, occurred_at, user_email as email, event_name as event_type, 'product' as source
    from {{ ref('stg_product_events') }}
    union all
    select event_id, occurred_at, contact_email, event_name, 'marketing'
    from {{ ref('stg_marketing_events') }}
),

email_resolved as (
    select
        e.event_id,
        e.occurred_at,
        e.occurred_at as known_at,
        e.event_type,
        e.source,
        c.contact_id,
        coalesce(c.account_id, a.account_id) as account_id,
        coalesce(c.contact_id, 'email:' || e.email) as person_key,
        coalesce(c.contact_id, 'email:' || e.email) as observed_key,
        e.occurred_at as person_known_at,
        case when c.contact_id is not null then 'email' when a.account_id is not null then 'email_domain' end as resolution_method
    from email_events e
    left join contacts c on c.email = e.email
    left join accounts a on a.domain = split_part(e.email, '@', 2)
)

select * from web_resolved
union all
select * from email_resolved
