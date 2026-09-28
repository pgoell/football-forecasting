select o.match_id, o.bookmaker, o.available_at, m.kickoff_at
from {{ ref('int_odds') }} as o
inner join {{ ref('stg_football_data__matches') }} as m using (match_id)
where o.moment = 'pre' and o.available_at > m.kickoff_at
