-- goalscorers.csv lists every goal, each with a minute, for every WC and EURO
-- finals match from 2006, so each has a 90-minute score. Warns and lists gaps.
{{ config(severity='warn') }}
with failures as (
    select match_id, match_date, home_team, away_team
    from {{ ref('stg_international_results__matches') }}
    where finals is not null and edition >= 2006 and not goals_complete
)

{{ holdout_silent('failures') }}
