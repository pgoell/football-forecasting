-- Odds with the time they became known and margin-free probabilities.
--
-- available_at, pre: Football-Data collects weekend odds (Fri to Mon matches)
-- on Friday by 17:00 UK time and midweek odds (Tue to Thu) on Tuesday by 13:00.
-- The rule is stated on football-data.co.uk/matches.php; whether it held in
-- every season, holidays included, is unverified.
-- available_at, close: kickoff; end of match day where kickoff time is unknown
-- (before 2019/20).
with joined as (
    select
        o.*,
        m.match_date,
        m.kickoff_at,
        dayofweek(m.match_date) as dow  -- 0 = Sunday
    from {{ ref('stg_football_data__odds') }} as o
    inner join {{ ref('stg_football_data__matches') }} as m using (match_id)
),

timed as (
    select
        *,
        case moment
            when 'pre' then least(
                timezone(
                    'Europe/London',
                    case
                        when dow in (5, 6, 0, 1) then (match_date - ((dow + 2) % 7)::int) + time '17:00'
                        else (match_date - (dow - 2)::int) + time '13:00'
                    end
                ),
                coalesce(kickoff_at, timezone('Europe/London', match_date + interval 1 day))
            )
            when 'close' then coalesce(kickoff_at, timezone('Europe/London', match_date + interval 1 day))
        end as available_at,
        1 / odds_home + 1 / odds_draw + 1 / odds_away as overround
    from joined
)

select
    match_id,
    bookmaker,
    moment,
    available_at,
    odds_home,
    odds_draw,
    odds_away,
    overround,
    (1 / odds_home) / overround as p_home,
    (1 / odds_draw) / overround as p_draw,
    (1 / odds_away) / overround as p_away
from timed
