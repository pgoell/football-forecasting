-- A team cannot have more goals at 90 minutes than at the end.
with failures as (
    select match_id, match_date, home_team, away_team
    from {{ ref('stg_international_results__matches') }}
    where home_score_90 > home_score or away_score_90 > away_score
)

{{ holdout_silent('failures') }}
