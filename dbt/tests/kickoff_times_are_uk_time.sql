-- Football-Data gives kickoff times in UK time (not stated by the source;
-- inferred). The Bundesliga's standard Saturday kickoff is 15:30 German time,
-- which is 14:30 UK time; it must be the most common D1 Saturday time.
with d1_saturday as (
    select kickoff_time, count(*) as n
    from {{ ref('stg_football_data__matches') }}
    where league = 'D1' and dayofweek(match_date) = 6 and kickoff_time is not null
    group by kickoff_time
)

select *
from d1_saturday
qualify n = max(n) over () and kickoff_time <> time '14:30'
