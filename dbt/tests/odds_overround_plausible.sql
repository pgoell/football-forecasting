-- Single bookmakers should price a margin of 0 to 30%. Aggregates (Max) can dip
-- below 1. Warns rather than fails: a few source rows are known to be off.
{{ config(severity='warn') }}
select o.*
from {{ ref('int_odds') }} as o
inner join {{ ref('bookmakers') }} as b on o.bookmaker = b.code
where not b.is_aggregate and o.overround not between 0.99 and 1.3
