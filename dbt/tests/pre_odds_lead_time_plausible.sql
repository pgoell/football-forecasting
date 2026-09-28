-- Pre-match odds become known 0 to 4 days before kickoff under the
-- Friday/Tuesday collection rule (Friday 17:00 for a Monday match is ~75h).
select o.match_id, o.bookmaker, o.available_at, m.kickoff_at
from {{ ref('int_odds') }} as o
inner join {{ ref('stg_football_data__matches') }} as m using (match_id)
where o.moment = 'pre'
    and m.kickoff_at is not null
    and (o.available_at > m.kickoff_at or o.available_at < m.kickoff_at - interval 96 hours)
