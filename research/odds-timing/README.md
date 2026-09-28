# Odds timing check

Checks when Football-Data collected its pre-match odds, season by season, against copies of its pages and files in the Internet Archive. Run on 2026-09-28 against the data version recorded in `dbt/seeds/football_data_files.csv` at that date. Findings: [docs/data-sources.md](../../docs/data-sources.md#pre-match-odds-collection-time-checked-tested-for-plausibility).

## Method

1. `rules.py` prints the collection-time wording in every archived copy of `notes.txt` and `matches.php`.
2. `res.py` fetches every archived copy of `fixtures.csv`, `fixtures.xls` and the in-season `mmz4281/<ssss>/<E0|D1>.csv` files. For each E0/D1 match in a copy it records the capture time, our modeled `available_at` (`fix.rule`), whether the copy had odds, and whether those odds differ from the final file in `data/raw/`. Output: `res_res.json`.
3. `evidence.csv` is `res_res.json` flattened, one row per match per copy (`n_diff` = odds that differ from the final file).

An archived copy captured at time T that holds odds proves the odds existed by T. It cannot pin collection to the hour: copies fall days apart.

## Rerun

```sh
cd research/odds-timing
uv run rules.py      # stated rule over time
uv run res.py        # evidence, ~250 requests at 1.2s each, cached in cache/
```

`cdx/` holds the Internet Archive index listings the scripts read, fetched from `http://web.archive.org/cdx/search/cdx?url=<url>&output=json` for `football-data.co.uk/fixtures.csv`, `football-data.co.uk/mmz4281/*`, `notes.txt` and `matches.php`. A rerun from the cache reproduced `res_res.json` exactly (40,434 rows).
