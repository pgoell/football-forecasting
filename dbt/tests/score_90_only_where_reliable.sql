-- A 90-minute score only where it can be trusted: every goal listed with a
-- minute, not awarded, and outside WC and EURO finals no goal after minute 90
-- (docs/data-sources.md).
with failures as (
    select match_id, match_date, home_team, away_team
    from {{ ref('stg_international_results__matches') }}
    where (home_score_90 is not null) <> score_90_reliable
        or (away_score_90 is not null) <> score_90_reliable
        or (score_90_reliable and (not goals_complete or awarded or (finals is null and after_90 > 0)))
)

{{ holdout_silent('failures') }}
