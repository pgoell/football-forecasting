-- One row per match.
with typed as (
    select
        Div as league,
        season,
        match_date,
        Time::time as kickoff_time,
        HomeTeam as home_team,
        AwayTeam as away_team,
        FTHG::int as home_goals,
        FTAG::int as away_goals,
        FTR as result,
        HTHG::int as home_goals_ht,
        HTAG::int as away_goals_ht,
        HS::int as home_shots,
        "AS"::int as away_shots,
        HST::int as home_shots_on_target,
        AST::int as away_shots_on_target
    from {{ ref('base_football_data') }}
)

select
    {{ match_id('league', 'match_date', 'home_team') }} as match_id,
    *,
    timezone('Europe/London', match_date + kickoff_time) as kickoff_at
from typed
