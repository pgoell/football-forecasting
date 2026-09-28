-- The martj42 CSVs on disk are the ones recorded in seeds/international_results_files.csv.
-- Warns: a download from a new commit changes them; commit the updated seed.
{{ config(severity='warn') }}
with on_disk as (
    select regexp_extract(filename, '([a-z_]+\.csv)$', 1) as file, sha256(content) as sha256
    from read_text('{{ var("raw_dir") }}/international-results/*.csv')
)

select coalesce(d.file, r.file) as file, d.sha256 as on_disk, r.sha256 as recorded
from on_disk as d
full outer join {{ ref('international_results_files') }} as r using (file)
where d.sha256 is distinct from r.sha256
