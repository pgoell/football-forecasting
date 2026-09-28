select match_id, bookmaker, moment, count(*) as n
from {{ ref('stg_football_data__odds') }}
group by all
having count(*) > 1
