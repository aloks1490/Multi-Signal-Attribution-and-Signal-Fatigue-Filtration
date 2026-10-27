{# Exponential decay: weight halves every half_life days. age_days may be fractional. #}
{% macro decay(weight, half_life, age_days) -%}
    ({{ weight }} * power(2.0, -1.0 * ({{ age_days }}) / {{ half_life }}))
{%- endmacro %}

{# Fractional days between an event timestamp and the start of a score date. #}
{% macro age_days(score_date, ts) -%}
    (epoch(cast({{ score_date }} as timestamp)) - epoch({{ ts }})) / 86400.0
{%- endmacro %}
