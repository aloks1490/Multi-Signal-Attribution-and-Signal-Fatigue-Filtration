-- ICP fit from fit_rules: points per matched rule, then a grade and multiplier from fit_grades. Does not decay.
with accounts as (
    select * from {{ ref('stg_accounts') }}
),

attributes as (
    select account_id, 'employee_count' as attribute, cast(employee_count as double) as num_value, cast(null as varchar) as str_value from accounts
    union all select account_id, 'sales_headcount', cast(sales_headcount as double), null from accounts
    union all select account_id, 'industry', null, industry from accounts
    union all select account_id, 'region', null, region from accounts
    union all select account_id, 'crm', null, crm from accounts
),

matched as (
    select attr.account_id, r.rule, r.points
    from attributes attr
    join {{ ref('fit_rules') }} r on r.attribute = attr.attribute
    where (r.match_type = 'range' and attr.num_value between r.min_value and r.max_value)
       or (r.match_type = 'in_list' and list_contains(string_split(r.list_values, '|'), attr.str_value))
),

points as (
    select a.account_id, coalesce(sum(m.points), 0) as fit_points
    from accounts a
    left join matched m on m.account_id = a.account_id
    group by a.account_id
)

select
    p.account_id,
    p.fit_points,
    g.grade as fit_grade,
    g.multiplier as fit_multiplier
from points p
join {{ ref('fit_grades') }} g on p.fit_points between g.min_points and g.max_points
