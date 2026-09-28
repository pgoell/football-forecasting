-- depends_on: {{ ref('base_football_data') }}
-- 1X2 odds, one row per match, bookmaker and moment. Football-Data names the
-- columns <code>H/D/A for the pre-match snapshot and <code>CH/CD/CA for
-- closing. A code's columns exist only in the seasons that carry it; rows
-- without all three prices are dropped, and so are rows with a price of 1 or
-- less (5 bet365 pre rows in E1 and E2 carry a home price of 0).
{%- set columns = adapter.get_columns_in_relation(ref('base_football_data')) | map(attribute='name') | list if execute else [] %}
{%- set selects = [] %}
{%- for code in var('football_data_bookmakers') %}
{%- for moment, infix in [('pre', ''), ('close', 'C')] %}
{%- if (code ~ infix ~ 'H') in columns %}
{%- do selects.append(
    "select " ~ match_id('Div', 'match_date', 'HomeTeam') ~ " as match_id, '" ~ code ~ "' as bookmaker, '" ~ moment ~ "' as moment, "
    ~ "try_cast(\"" ~ code ~ infix ~ "H\" as double) as odds_home, "
    ~ "try_cast(\"" ~ code ~ infix ~ "D\" as double) as odds_draw, "
    ~ "try_cast(\"" ~ code ~ infix ~ "A\" as double) as odds_away "
    ~ "from " ~ ref('base_football_data')
) %}
{%- endif %}
{%- endfor %}
{%- endfor %}

with long as (
    {{ selects | join('\n    union all\n    ') }}
)

select *
from long
where odds_home is not null and odds_draw is not null and odds_away is not null
    and least(odds_home, odds_draw, odds_away) > 1
