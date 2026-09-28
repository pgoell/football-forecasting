-- In WC and EURO finals from 2006, goalscorers.csv records stoppage time as
-- minute 45 or 90 and extra time as 91 to 120. If a stoppage goal were
-- recorded as 91 or later, its match would not be level at 90 minutes, and a
-- finals match not level at 90 has no extra time. (Not true of every match:
-- 2003 to 2005 World Cup qualifiers have stoppage goals at 91 to 95, and a
-- second leg can go to extra time without being level; docs/data-sources.md.)
with goals as (
    select date::date as match_date, home_team, away_team, team, try_cast(minute as int) as minute
    from read_csv(
        '{{ var("raw_dir") }}/international-results/goalscorers.csv', header = true, all_varchar = true
    )
),

finals as (
    select match_date, home_team, away_team
    from {{ ref('stg_international_results__matches') }}
    where finals is not null and edition >= 2006
),

failures as (
    select match_date, home_team, away_team
    from goals
    inner join finals using (match_date, home_team, away_team)
    group by all
    having count(*) filter (where minute > 90) > 0
        and count(*) filter (where minute <= 90 and team = home_team)
        <> count(*) filter (where minute <= 90 and team = away_team)
)

{{ holdout_silent('failures') }}
