import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from football_forecasting import euro2028 as e2028


def warehouse(tmp_path: Path, elo_rows: list[tuple], names: dict[str, str]) -> Path:
    """A minimal warehouse: `stg_eloratings__matches` (team1_id, team2_id, match_date,
    rating1_post, rating2_post) and `team_names` (team_id, martj42_name), the only tables
    `euro2028.py` reads."""
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        """
        create table stg_eloratings__matches (
            team1_id varchar, team2_id varchar, match_date date,
            rating1_post integer, rating2_post integer
        )
        """
    )
    if elo_rows:
        con.executemany("insert into stg_eloratings__matches values (?, ?, ?, ?, ?)", elo_rows)
    con.execute("create table team_names (team_id varchar, martj42_name varchar)")
    if names:
        con.executemany("insert into team_names values (?, ?)", list(names.items()))
    con.close()
    return path


def test_hosts_are_the_euro2028_hosts():
    assert e2028.hosts() == ("england", "scotland", "wales", "republic_of_ireland")


def test_uefa_teams_are_55_unique_members_including_the_hosts():
    assert len(e2028.UEFA_TEAMS) == 55
    assert len(set(e2028.UEFA_TEAMS)) == 55
    assert set(e2028.hosts()) <= set(e2028.UEFA_TEAMS)


def test_current_ratings_takes_each_teams_most_recent_match(tmp_path):
    rows = [
        ("england", "spain", date(2026, 1, 1), 2000, 2200),
        ("england", "france", date(2026, 3, 1), 2050, 2070),  # england's latest: 2050
        ("spain", "france", date(2026, 6, 1), 2250, 2080),  # spain's and france's latest
    ]
    path = warehouse(tmp_path, rows, {})
    ratings = e2028.current_ratings(path)
    assert ratings == {"england": 2050, "spain": 2250, "france": 2080}


def test_table_puts_hosts_first_then_sorts_by_rating_and_drops_suspended_teams(tmp_path):
    rows = [
        ("england", "scotland", date(2026, 1, 1), 1700, 1600),
        ("wales", "spain", date(2026, 1, 2), 1500, 2200),
        ("republic_of_ireland", "russia", date(2026, 1, 3), 1400, 1900),
    ]
    names = {
        "england": "England",
        "scotland": "Scotland",
        "wales": "Wales",
        "spain": "Spain",
        "republic_of_ireland": "Republic of Ireland",
        "russia": "Russia",
    }
    path = warehouse(tmp_path, rows, names)
    rows_out = e2028.table(path)
    teams = [r.team for r in rows_out]
    assert "russia" not in teams  # suspended, docs/data-sources.md
    assert teams[:4] == ["england", "scotland", "wales", "republic_of_ireland"]  # hosts first
    assert [r.is_host for r in rows_out[:4]] == [True, True, True, True]
    assert teams[4] == "spain"  # highest-rated non-host (2200)
    hosts_ratings = [r.rating for r in rows_out[:4]]
    assert hosts_ratings == sorted(hosts_ratings, reverse=True)  # hosts sorted by rating too


def test_snapshot_and_save_are_immutable(tmp_path):
    rows = [e2028.TeamRating("england", "England", 2100.0, True)]
    as_of = datetime(2026, 9, 28, tzinfo=UTC)
    snap = e2028.snapshot(rows, as_of)
    assert len(snap) == 1
    path = tmp_path / "p.duckdb"
    assert e2028.save_snapshot(snap, path) == 1
    assert e2028.save_snapshot(snap, path) == 0  # rerun: nothing new
    changed = [dataclasses.replace(snap[0], rating=1.0)]
    with pytest.raises(ValueError, match="would change"):
        e2028.save_snapshot(changed, path)


def test_latest_snapshot_reads_back_what_was_saved(tmp_path):
    warehouse_path = warehouse(
        tmp_path, [("england", "spain", date(2026, 1, 1), 2100, 2200)], {"england": "England"}
    )
    predictions_path = tmp_path / "p.duckdb"
    rows = [e2028.TeamRating("england", "England", 2100.0, True)]
    as_of = datetime(2026, 9, 28, tzinfo=UTC)
    e2028.save_snapshot(e2028.snapshot(rows, as_of), predictions_path)
    rows_out, stored_as_of = e2028.latest_snapshot(warehouse_path, predictions_path)
    assert stored_as_of == as_of
    assert rows_out == [e2028.TeamRating("england", "England", 2100.0, True)]


def test_latest_snapshot_empty_before_any_run(tmp_path):
    warehouse_path = warehouse(tmp_path, [], {})
    predictions_path = tmp_path / "p.duckdb"
    duckdb.connect(str(predictions_path)).close()  # exists, but no euro2028_ratings table yet
    rows_out, as_of = e2028.latest_snapshot(warehouse_path, predictions_path)
    assert rows_out == []
    assert as_of is None
