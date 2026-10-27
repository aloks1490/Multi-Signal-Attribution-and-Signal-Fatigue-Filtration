{# Scalar lookup into the scoring_params seed, e.g. {{ param('rearm_days', 'integer') }} #}
{% macro param(name, type='double') -%}
    (select cast(value as {{ type }}) from {{ ref('scoring_params') }} where param = '{{ name }}')
{%- endmacro %}
