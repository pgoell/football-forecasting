-- martj42 matches with the eloratings.net match of the same date and teams,
-- turned to martj42's home and away. Where the two sources put a match one or
-- two days apart (74 matches, docs/data-sources.md), the
-- nearest eloratings.net match of the same teams counts, if no other martj42
-- match took it. Elo columns are null where eloratings.net has no such match
-- or a team is not in seeds/team_names.csv.
with elo as (
    select
        seq,
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
        seq,
        match_date,
        team2_id,
        team1_id,
        score2,
        score1,
        rating2_pre,
        rating1_pre
    from {{ ref('stg_eloratings__matches') }}
),

same_day as (
    select m.match_id, e.*
    from {{ ref('stg_international_results__matches') }} as m
    inner join elo as e using (match_date, home_team_id, away_team_id)
),

near_day as (
    select m.match_id, e.*
    from {{ ref('stg_international_results__matches') }} as m
    inner join elo as e
        on m.home_team_id = e.home_team_id
        and m.away_team_id = e.away_team_id
        and abs(e.match_date - m.match_date) between 1 and 2
    where m.match_id not in (select match_id from same_day)
        and e.seq not in (select seq from same_day)
    qualify row_number() over (partition by m.match_id order by abs(e.match_date - m.match_date)) = 1
        and row_number() over (partition by e.seq order by abs(e.match_date - m.match_date)) = 1
),

matched as (
    select * from same_day
    union all
    select * from near_day
)

select
    m.*,
    e.match_date as elo_match_date,
    e.home_score as elo_home_score,
    e.away_score as elo_away_score,
    e.home_rating_pre as elo_home_rating_pre,
    e.away_rating_pre as elo_away_rating_pre
from {{ ref('stg_international_results__matches') }} as m
left join matched as e using (match_id)
