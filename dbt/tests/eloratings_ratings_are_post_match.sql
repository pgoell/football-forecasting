-- The two rating columns of the eloratings.net files are ratings after the
-- match: a team's rating after one match plus its change in the next equals
-- its rating after the next, in file order (the files are in date order).
-- Returns a count only, as it spans the holdout.
with team_matches as (
    select seq, match_date, code1 as code, change, rating1_post as post from {{ ref('stg_eloratings__matches') }}
    union all
    select seq, match_date, code2, -change, rating2_post from {{ ref('stg_eloratings__matches') }}
),

steps as (
    select post, change, lag(post) over (partition by code order by seq) as previous_post
    from team_matches
)

select count(*) as failures
from steps
where previous_post + change <> post
having count(*) > 0
