-- Every finished season has 380 E0 or 306 D1 matches. The current season (2627) is still running.
select league, season, count(*) as matches
from {{ ref('stg_football_data__matches') }}
where season <> '2627'
group by league, season
having count(*) <> case league when 'E0' then 380 when 'D1' then 306 end
