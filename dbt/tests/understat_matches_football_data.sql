-- Every E0 and D1 Football-Data match from 2014/15 on has exactly one played Understat
-- match with the same league, season and teams, and the same score; and every
-- played Understat match has a Football-Data match, except in the running
-- season, where the two downloads may be a matchday apart.
-- Known score difference: D1 Union Berlin v Bochum, 14/12/2024, played 1-1,
-- awarded 0-2 (Football-Data carries the awarded score).
with understat as (
    select * from {{ ref('stg_understat__matches') }} where is_result
),

joined as (
    select
        coalesce(f.league, u.league) as league,
        coalesce(f.season, u.season) as season,
        coalesce(f.home_team, u.home_team) as home_team,
        coalesce(f.away_team, u.away_team) as away_team,
        f.match_id,
        u.understat_id,
        f.home_goals as fd_home,
        f.away_goals as fd_away,
        u.home_goals as us_home,
        u.away_goals as us_away,
        count(*) over (partition by f.match_id) as understat_rows
    from (
        select * from {{ ref('stg_football_data__matches') }} where league in ('E0', 'D1')
    ) as f
    full outer join understat as u using (league, season, home_team, away_team)
    where coalesce(f.season, u.season) >= '1415'
)

select *
from joined
where understat_id is null
    or (match_id is null and season <> '2627')
    or understat_rows > 1
    or (
        (fd_home, fd_away) is distinct from (us_home, us_away)
        and match_id <> 'D1_20241214_Union Berlin'
    )
