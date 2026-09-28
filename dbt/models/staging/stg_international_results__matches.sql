-- One row per match in martj42/international_results. Scores include extra
-- time, not shootouts. The 90-minute score comes from goalscorers.csv: it
-- records stoppage time as minute 45 or 90 and extra time as 91 to 120
-- (docs/data-sources.md), so goals at minute 90 or before make the 90-minute
-- score. It is null when the listed goals do not add up to the full score.
with results as (
    select *
    from read_csv(
        '{{ var("raw_dir") }}/international-results/results.csv', header = true, all_varchar = true
    )
),

goals as (
    select
        date,
        home_team,
        away_team,
        count(*) filter (where team = home_team) as home_listed,
        count(*) filter (where team = away_team) as away_listed,
        count(*) filter (where team = home_team and try_cast(minute as int) <= 90) as home_90,
        count(*) filter (where team = away_team and try_cast(minute as int) <= 90) as away_90,
        count(*) filter (where try_cast(minute as int) is null) as no_minute
    from read_csv(
        '{{ var("raw_dir") }}/international-results/goalscorers.csv', header = true, all_varchar = true
    )
    group by all
),

shootouts as (
    select date, home_team, away_team, winner
    from read_csv(
        '{{ var("raw_dir") }}/international-results/shootouts.csv', header = true, all_varchar = true
    )
),

typed as (
    select
        r.date::date as match_date,
        r.home_team,
        r.away_team,
        r.home_score::int as home_score,
        r.away_score::int as away_score,
        r.tournament,
        r.city,
        r.country,
        r.neutral = 'TRUE' as neutral,
        s.winner as shootout_winner,
        coalesce(g.home_listed, 0) = r.home_score::int
            and coalesce(g.away_listed, 0) = r.away_score::int
            and coalesce(g.no_minute, 0) = 0 as goals_complete,
        g.home_90,
        g.away_90
    from results as r
    left join goals as g using (date, home_team, away_team)
    left join shootouts as s using (date, home_team, away_team)
)

select
    -- a few pairs met twice on one day (Tahiti v New Caledonia, 1974-02-17)
    strftime(t.match_date, '%Y%m%d') || '_' || t.home_team || '_' || t.away_team
    || coalesce('_' || nullif(row_number() over (partition by t.match_date, t.home_team, t.away_team), 1), '')
        as match_id,
    t.match_date,
    t.home_team,
    t.away_team,
    h.team_id as home_team_id,
    a.team_id as away_team_id,
    t.home_score,
    t.away_score,
    case when t.goals_complete then coalesce(t.home_90, 0) end as home_score_90,
    case when t.goals_complete then coalesce(t.away_90, 0) end as away_score_90,
    t.goals_complete,
    t.shootout_winner,
    t.tournament,
    case t.tournament when 'FIFA World Cup' then 'WC' when 'UEFA Euro' then 'EURO' end as finals,
    -- EURO 2020 was played in 2021
    case
        when t.tournament = 'UEFA Euro' and year(t.match_date) = 2021 then 2020
        when t.tournament in ('FIFA World Cup', 'UEFA Euro') then year(t.match_date)
    end as edition,
    t.city,
    t.country,
    t.neutral
from typed as t
left join {{ ref('team_names') }} as h on t.home_team = h.martj42_name
left join {{ ref('team_names') }} as a on t.away_team = a.martj42_name
