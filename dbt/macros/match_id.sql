{% macro match_id(league, match_date, home_team) -%}
    {{ league }} || '_' || strftime({{ match_date }}, '%Y%m%d') || '_' || {{ home_team }}
{%- endmacro %}
