-- Catches encoding damage: a replacement character or UTF-8 read as Latin-1.
select distinct home_team as team
from {{ ref('stg_football_data__matches') }}
where home_team like '%' || chr(65533) || '%' or home_team like '%Ã%'
