-- Each finals tournament from 2006 has all its matches: 64 per World Cup to
-- 2022, 104 in 2026 (48 teams); 31 per EURO in 2008 and 2012, 51 from 2016 (24 teams).
with expected as (
    select * from (values
        ('WC', 2006, 64), ('WC', 2010, 64), ('WC', 2014, 64), ('WC', 2018, 64), ('WC', 2022, 64),
        ('WC', 2026, 104),
        ('EURO', 2008, 31), ('EURO', 2012, 31), ('EURO', 2016, 51), ('EURO', 2020, 51),
        ('EURO', 2024, 51)
    ) as t (finals, edition, matches)
),

actual as (
    select finals, edition, count(*) as matches
    from {{ ref('stg_international_results__matches') }}
    where edition >= 2006
    group by all
)

select coalesce(e.finals, a.finals) as finals, coalesce(e.edition, a.edition) as edition,
    e.matches as expected, a.matches as actual
from expected as e
full outer join actual as a using (finals, edition)
where e.matches is distinct from a.matches
