{# Failing rows of `failures` (a CTE with match_date): in full up to the end of
   validation, and after it only as a count, so no holdout result is shown
   (docs/tournament-spec.md). #}
{% macro holdout_silent(failures) -%}
    select * from {{ failures }} where match_date <= date '2024-07-14'
    union all by name
    select count(*) as holdout_failures
    from {{ failures }}
    where match_date > date '2024-07-14' or match_date is null
    having count(*) > 0
{%- endmacro %}
