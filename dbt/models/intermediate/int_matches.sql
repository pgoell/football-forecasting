-- One row per match with the times its data becomes known.
--
-- pre_at: Football-Data collects weekend odds (Fri to Mon matches) on Friday by
-- 17:00 UK time and midweek odds (Tue to Thu) on Tuesday by 13:00
-- (football-data.co.uk/matches.php). Before 2017/18 the site said Tuesday
-- 15:00, so midweek uses 15:00 for those seasons. Checked against archived
-- copies of the files in research/odds-timing/; see docs/data-sources.md.
-- Capped at kickoff.
-- close_at: kickoff; end of match day where kickoff time is unknown (before 2019/20).
-- result_at: end of match day, for every match, so no result counts as known
-- before the day's last kickoff.
-- pre_timing_uncertain: matches from 20 Dec to 5 Jan, where archived files
-- point to odd collection batches.
-- rest_days, matches_14d: days since the team's previous match and its matches
-- in the 14 days before, from fixture dates, so known before the match. League
-- matches only: the files have no cup or European games.
with team_days as (
    select match_id, 'home' as side, home_team as team, match_date
    from {{ ref('stg_football_data__matches') }}
    union all
    select match_id, 'away', away_team, match_date
    from {{ ref('stg_football_data__matches') }}
),

rest as (
    select
        match_id,
        side,
        match_date - lag(match_date) over w as rest_days,
        count(*) over (
            w range between interval 14 days preceding and interval 1 day preceding
        ) as matches_14d
    from team_days
    window w as (partition by team order by match_date)
),

matches as (
    select
        m.*,
        dayofweek(m.match_date) as dow,  -- 0 = Sunday
        timezone('Europe/London', m.match_date + interval 1 day) as end_of_day,
        h.rest_days as home_rest_days,
        a.rest_days as away_rest_days,
        h.matches_14d as home_matches_14d,
        a.matches_14d as away_matches_14d
    from {{ ref('stg_football_data__matches') }} as m
    inner join rest as h on m.match_id = h.match_id and h.side = 'home'
    inner join rest as a on m.match_id = a.match_id and a.side = 'away'
)

select
    match_id,
    league,
    season,
    match_date,
    kickoff_at,
    home_team,
    away_team,
    home_goals,
    away_goals,
    result,
    home_shots,
    away_shots,
    home_shots_on_target,
    away_shots_on_target,
    home_rest_days,
    away_rest_days,
    home_matches_14d,
    away_matches_14d,
    least(
        timezone(
            'Europe/London',
            case
                when dow in (5, 6, 0, 1) then (match_date - ((dow + 2) % 7)::int) + time '17:00'
                when season < '1718' then (match_date - (dow - 2)::int) + time '15:00'
                else (match_date - (dow - 2)::int) + time '13:00'
            end
        ),
        coalesce(kickoff_at, end_of_day)
    ) as pre_at,
    coalesce(kickoff_at, end_of_day) as close_at,
    end_of_day as result_at,
    (month(match_date) = 12 and day(match_date) >= 20)
    or (month(match_date) = 1 and day(match_date) <= 5) as pre_timing_uncertain
from matches
