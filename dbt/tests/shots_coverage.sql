-- Shots and shots on target, E0 and D1 (the only leagues whose models use
-- them): every match of a season has them, or none does.
-- Known gaps: D1 2002/03 has no shots; D1 2003/04 to 2005/06 have shots but
-- not shots on target; D1 Union Berlin v Bochum on 14/12/2024 has none (an
-- awarded result, 0-2 in the file).
with seasons as (
    select
        league,
        season,
        count(*) as matches,
        count(home_shots) + count(away_shots) as shots,
        count(home_shots_on_target) + count(away_shots_on_target) as on_target
    from {{ ref('stg_football_data__matches') }}
    where league in ('E0', 'D1') and match_id <> 'D1_20241214_Union Berlin'
    group by all
),

expected as (
    select
        *,
        not (league = 'D1' and season = '0203') as has_shots,
        not (league = 'D1' and season between '0203' and '0506') as has_on_target
    from seasons
)

select *
from expected
where shots <> case when has_shots then 2 * matches else 0 end
    or on_target <> case when has_on_target then 2 * matches else 0 end
