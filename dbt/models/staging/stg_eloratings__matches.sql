-- One row per match in the eloratings.net <year>_results.tsv files. Column
-- meanings are read from the site's scripts/ratings.js and checked against the
-- data (docs/data-sources.md): the ratings are after the match, and the change
-- is the points team 1 gained, so pre-match ratings are post minus change for
-- team 1 and post plus change for team 2. Old codes (teams.tsv) become the
-- current code, as the site does.
with raw as (
    -- file order, which orders a team's two matches on one day
    select *, row_number() over () as seq
    from read_csv(
        '{{ var("raw_dir") }}/eloratings/*_results.tsv',
        delim = '\t',
        header = false,
        quote = '',
        columns = {
            'y': 'varchar', 'm': 'varchar', 'd': 'varchar',
            'code1': 'varchar', 'code2': 'varchar', 'score1': 'varchar', 'score2': 'varchar',
            'tournament': 'varchar', 'venue': 'varchar', 'change': 'varchar',
            'post1': 'varchar', 'post2': 'varchar', 'rank_move1': 'varchar', 'rank_move2': 'varchar',
            'rank1': 'varchar', 'rank2': 'varchar'
        }
    )
),

old_codes as (
    select *
    from read_csv(
        '{{ var("raw_dir") }}/eloratings/teams.tsv',
        delim = '\t',
        header = false,
        quote = '',
        columns = {'old': 'varchar', 'current': 'varchar'}
    )
),

typed as (
    select
        seq,
        -- day 00 marks an unknown day (one 2004 match); its date is null
        try_strptime(y || '-' || m || '-' || d, '%Y-%m-%d')::date as match_date,
        coalesce(o1.current, raw.code1) as code1,
        coalesce(o2.current, raw.code2) as code2,
        score1::int as score1,
        score2::int as score2,
        tournament,
        venue,
        replace(change, '−', '-')::int as change,
        post1::int as post1,
        post2::int as post2
    from raw
    left join old_codes as o1 on raw.code1 = o1.old
    left join old_codes as o2 on raw.code2 = o2.old
)

select
    t.seq,
    t.match_date,
    t.code1,
    t.code2,
    n1.team_id as team1_id,
    n2.team_id as team2_id,
    t.score1,
    t.score2,
    t.tournament,
    t.venue,
    t.change,
    t.post1 - t.change as rating1_pre,
    t.post2 + t.change as rating2_pre,
    t.post1 as rating1_post,
    t.post2 as rating2_post
from typed as t
left join {{ ref('team_names') }} as n1 on t.code1 = n1.eloratings_code
left join {{ ref('team_names') }} as n2 on t.code2 = n2.eloratings_code
