-- Every finished season has the matches seeds/leagues.csv expects. The current
-- season (2627) is still running. E2 2019/20 has 400: the season stopped in
-- March 2020 (COVID) and Bury, expelled before it began, played none.
select m.league, m.season, count(*) as matches
from {{ ref('stg_football_data__matches') }} as m
inner join {{ ref('leagues') }} as l using (league)
where m.season <> '2627'
group by m.league, m.season, l.matches_per_season
having count(*) <> case when m.league = 'E2' and m.season = '1920' then 400 else l.matches_per_season end
