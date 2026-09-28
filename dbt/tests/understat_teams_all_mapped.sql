-- Every E0 and D1 team from 2014/15 on has an Understat name.
select distinct m.league, m.home_team
from {{ ref('stg_football_data__matches') }} as m
left join {{ ref('understat_team_names') }} as n
    on m.league = n.league and m.home_team = n.football_data_name
where m.season >= '1415' and n.understat_name is null
