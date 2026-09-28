-- Odds with the time they became known and margin-free probabilities.
--
-- available_at: int_matches.pre_at or close_at, by moment; see int_matches.
-- pre_timing_uncertain: pre odds of matches int_matches flags.
-- is_reliable: false from the bookmaker's unreliable_from date in the
-- bookmaker_unreliable_periods seed (Pinnacle since 23/07/2025, per football-data.co.uk/data.php).
with joined as (
    select
        o.*,
        m.match_date,
        u.unreliable_from,
        case o.moment when 'pre' then m.pre_at when 'close' then m.close_at end as available_at,
        o.moment = 'pre' and m.pre_timing_uncertain as pre_timing_uncertain,
        1 / o.odds_home + 1 / o.odds_draw + 1 / o.odds_away as overround
    from {{ ref('stg_football_data__odds') }} as o
    inner join {{ ref('int_matches') }} as m using (match_id)
    left join {{ ref('bookmaker_unreliable_periods') }} as u on o.bookmaker = u.code
)

select
    match_id,
    bookmaker,
    moment,
    available_at,
    pre_timing_uncertain,
    coalesce(match_date < unreliable_from, true) as is_reliable,
    odds_home,
    odds_draw,
    odds_away,
    overround,
    (1 / odds_home) / overround as p_home,
    (1 / odds_draw) / overround as p_draw,
    (1 / odds_away) / overround as p_away
from joined
