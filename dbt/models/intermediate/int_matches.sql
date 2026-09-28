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
with matches as (
    select
        *,
        dayofweek(match_date) as dow,  -- 0 = Sunday
        timezone('Europe/London', match_date + interval 1 day) as end_of_day
    from {{ ref('stg_football_data__matches') }}
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
