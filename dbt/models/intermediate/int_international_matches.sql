-- martj42 matches with the eloratings.net match of the same date and teams,
-- turned to martj42's home and away. Elo columns are null where eloratings.net
-- has no such match or a team is not in seeds/team_names.csv.
with elo as (
    select
        match_date,
        team1_id as home_team_id,
        team2_id as away_team_id,
        score1 as home_score,
        score2 as away_score,
        rating1_pre as home_rating_pre,
        rating2_pre as away_rating_pre
    from {{ ref('stg_eloratings__matches') }}
    union all
    select
        match_date,
        team2_id,
        team1_id,
        score2,
        score1,
        rating2_pre,
        rating1_pre
    from {{ ref('stg_eloratings__matches') }}
)

select
    m.*,
    e.home_score as elo_home_score,
    e.away_score as elo_away_score,
    e.home_rating_pre as elo_home_rating_pre,
    e.away_rating_pre as elo_away_rating_pre
from {{ ref('stg_international_results__matches') }} as m
left join elo as e using (match_date, home_team_id, away_team_id)
