-- Every WC and EURO finals match from 2006 and every EURO qualifier from 2006
-- has both teams in seeds/team_names.csv and finds its eloratings.net match
-- (same date, same team ids), so both sources map to one id. Except Italy v
-- Serbia, 2010-10-12: abandoned after six minutes and awarded 3-0; eloratings.net
-- leaves it out.
with failures as (
    select match_id, match_date, home_team, away_team, home_team_id, away_team_id
    from {{ ref('int_international_matches') }}
    where match_date >= date '2006-01-01'
        and tournament in ('FIFA World Cup', 'UEFA Euro', 'UEFA Euro qualification')
        and match_id <> '20101012_Italy_Serbia'
        and (home_team_id is null or away_team_id is null or elo_home_rating_pre is null)
)

{{ holdout_silent('failures') }}
