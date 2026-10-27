select event_type
from {{ ref('signal_taxonomy') }}
where half_life_days <= 0 or weight < 0
