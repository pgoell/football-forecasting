-- Shots on target are a subset of shots. Warns: 3 source rows break it
-- (E0 Coventry 14/10/2000, Bradford 13/04/2001, Newcastle 15/08/2021).
{{ config(severity='warn') }}
select *
from {{ ref('stg_football_data__matches') }}
where home_shots_on_target > home_shots or away_shots_on_target > away_shots
