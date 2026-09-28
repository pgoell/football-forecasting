-- The Understat files on disk are the ones recorded in seeds/understat_files.csv.
-- Warns: a new download legitimately changes the running season's file.
{{ config(severity='warn') }}
with on_disk as (
    select
        regexp_extract(filename, '([A-Za-z]+)/(\d{4})\.json$', 1) as league,
        regexp_extract(filename, '([A-Za-z]+)/(\d{4})\.json$', 2) as season,
        sha256(content) as sha256
    from read_text('{{ var("raw_dir") }}/understat/*/*.json')
)

select coalesce(d.league, r.league) as league, coalesce(d.season, r.season) as season, d.sha256 as on_disk, r.sha256 as recorded
from on_disk as d
full outer join {{ ref('understat_files') }} as r using (league, season)
where d.sha256 is distinct from r.sha256
