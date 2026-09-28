select *
from {{ ref('stg_football_data__matches') }}
where result <> case
    when home_goals > away_goals then 'H'
    when home_goals < away_goals then 'A'
    else 'D'
end
