-- The eloratings.net files on disk are the ones recorded in seeds/eloratings_files.csv.
-- Warns: the site rewrites its files (the running year's with every match).
{{ config(severity='warn') }}
with on_disk as (
    select regexp_extract(filename, '([a-z0-9_.]+\.tsv)$', 1) as file, sha256(content) as sha256
    from read_text('{{ var("raw_dir") }}/eloratings/*.tsv')
)

select coalesce(d.file, r.file) as file, d.sha256 as on_disk, r.sha256 as recorded
from on_disk as d
full outer join {{ ref('eloratings_files') }} as r using (file)
where d.sha256 is distinct from r.sha256
