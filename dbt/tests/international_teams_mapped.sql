-- Every WC and EURO finals match from 2006 and every EURO qualifier from 2006
-- has both teams in seeds/team_names.csv and finds its eloratings.net match
-- (same date or one or two days apart, same team ids), so both sources map to
-- one id. Except awarded matches (Italy v Serbia, 2010-10-12, abandoned after
-- six minutes), which eloratings.net leaves out.
with failures as (
    select match_id, match_date, home_team, away_team, home_team_id, away_team_id
    from {{ ref('int_international_matches') }}
    where match_date >= date '2006-01-01'
        and tournament in ('FIFA World Cup', 'UEFA Euro', 'UEFA Euro qualification')
        and not awarded
        and (home_team_id is null or away_team_id is null or elo_home_rating_pre is null)
)

{{ holdout_silent('failures') }}
