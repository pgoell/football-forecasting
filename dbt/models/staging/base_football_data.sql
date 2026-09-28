-- Every row of every Football-Data CSV, as text. Files differ in columns per
-- season, so they are unioned by name; blank trailing rows are dropped.
select
    *,
    regexp_extract(filename, '(\d{4})\.csv$', 1) as season,
    case
        when length(Date) = 8 then strptime(Date, '%d/%m/%y')
        else strptime(Date, '%d/%m/%Y')
    end::date as match_date
from read_csv(
    '{{ var("raw_dir") }}/football-data/*/*.csv',
    union_by_name = true,
    filename = true,
    all_varchar = true,
    header = true,
    null_padding = true,
    strict_mode = false
)
where HomeTeam is not null
