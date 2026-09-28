-- martj42 and eloratings.net give the same full-time score (extra time
-- included, shootout excluded) for every WC and EURO finals match from 2006.
with failures as (
    select match_id, match_date, home_team, away_team
    from {{ ref('int_international_matches') }}
    where finals is not null and edition >= 2006
        and (home_score, away_score) is distinct from (elo_home_score, elo_away_score)
)

{{ holdout_silent('failures') }}
