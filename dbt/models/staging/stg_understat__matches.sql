-- One row per Understat match, E0 and D1, with team names as Football-Data
-- spells them (seeds/understat_team_names.csv). Understat serves numbers as text.
with raw as (
    select
        case regexp_extract(filename, '([A-Za-z]+)/\d{4}\.json$', 1)
            when 'EPL' then 'E0'
            when 'Bundesliga' then 'D1'
        end as league,
        regexp_extract(filename, '(\d{4})\.json$', 1)::int as start_year,
        unnest(dates) as m
    from read_json('{{ var("raw_dir") }}/understat/*/*.json', filename = true)
)

select
    raw.m.id as understat_id,
    raw.league,
    lpad((start_year % 100)::varchar, 2, '0') || lpad(((start_year + 1) % 100)::varchar, 2, '0')
        as season,
    raw.m.datetime as kickoff_local,
    h.football_data_name as home_team,
    a.football_data_name as away_team,
    raw.m.isResult as is_result,
    raw.m.goals.h::int as home_goals,
    raw.m.goals.a::int as away_goals,
    raw.m.xG.h::double as home_xg,
    raw.m.xG.a::double as away_xg
from raw
left join {{ ref('understat_team_names') }} as h
    on raw.league = h.league and raw.m.h.title = h.understat_name
left join {{ ref('understat_team_names') }} as a
    on raw.league = a.league and raw.m.a.title = a.understat_name
