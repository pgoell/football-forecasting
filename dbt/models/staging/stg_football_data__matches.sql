-- One row per match from the Football-Data CSVs.
-- Files differ in columns per season, so they are unioned by name, read as text,
-- and cast here. Blank trailing rows in some files are dropped.
with raw as (
    select *
    from read_csv(
        '{{ var("raw_dir") }}/football-data/*/*.csv',
        union_by_name = true,
        filename = true,
        all_varchar = true,
        header = true,
        null_padding = true,
        strict_mode = false
    )
    where HomeTeam is not null
),

typed as (
    select
        Div as league,
        regexp_extract(filename, '(\d{4})\.csv$', 1) as season,
        case
            when length(Date) = 8 then strptime(Date, '%d/%m/%y')
            else strptime(Date, '%d/%m/%Y')
        end::date as match_date,
        Time::time as kickoff_time,
        HomeTeam as home_team,
        AwayTeam as away_team,
        FTHG::int as home_goals,
        FTAG::int as away_goals,
        FTR as result,
        HTHG::int as home_goals_ht,
        HTAG::int as away_goals_ht
    from raw
)

select
    league || '_' || strftime(match_date, '%Y%m%d') || '_' || home_team as match_id,
    *
from typed
