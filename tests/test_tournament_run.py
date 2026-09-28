import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from football_forecasting.tournament import Format, Result
from football_forecasting.tournament_run import (
    bind_match_probs,
    eloratings_ratings_for,
    first_match_date,
    forecast,
    predictions,
    save,
    score_pool_before,
)

COLUMNS = """
    match_id varchar, match_date date, home_team_id varchar, away_team_id varchar,
    home_score integer, away_score integer, home_score_90 integer, away_score_90 integer,
    score_90_reliable boolean, neutral boolean, awarded boolean, tournament varchar,
    finals varchar, edition integer, elo_home_rating_pre integer, elo_away_rating_pre integer
"""


def row(
    match_id: str,
    match_date: date,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    *,
    neutral: bool = True,
    tournament: str = "Friendly",
    finals: str | None = None,
    edition: int | None = None,
    elo_home_rating_pre: int | None = None,
    elo_away_rating_pre: int | None = None,
) -> tuple:
    return (
        match_id,
        match_date,
        home,
        away,
        home_score,
        away_score,
        home_score,
        away_score,
        True,
        neutral,
        False,
        tournament,
        finals,
        edition,
        elo_home_rating_pre,
        elo_away_rating_pre,
    )


def warehouse(tmp_path: Path, rows: list[tuple]) -> Path:
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute(f"create table int_international_matches ({COLUMNS})")
    if rows:
        con.executemany(
            "insert into int_international_matches values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    con.close()
    return path


def small_format() -> Format:
    """One group of 4, single final between its top two: the smallest format `simulate`
    can run to a champion."""
    return Format(
        id="test2000",
        kind="EURO",
        year=2000,
        format_version="test-v1",
        hosts=(),
        groups={"A": ("a", "b", "c", "d")},
        third_place_advance=0,
        third_place_table=None,
        knockout_seeds=(("1A", "2A"),),
        tiebreak="euro",
    )


def test_first_match_date(tmp_path):
    rows = [
        row("m1", date(2020, 6, 12), "a", "b", 1, 0, finals="EURO", edition=2020),
        row("m2", date(2020, 6, 11), "c", "d", 2, 0, finals="EURO", edition=2020),
        row("m3", date(2020, 6, 10), "a", "c", 0, 0, finals="WC", edition=2022),
    ]
    path = warehouse(tmp_path, rows)
    assert first_match_date("EURO", 2020, path) == date(2020, 6, 11)


def test_first_match_date_raises_when_no_matches(tmp_path):
    path = warehouse(tmp_path, [])
    with pytest.raises(ValueError, match="no matches"):
        first_match_date("EURO", 2020, path)


def test_score_pool_before_splits_by_outcome_and_respects_cutoff(tmp_path):
    rows = [
        row("m1", date(2018, 1, 1), "a", "b", 2, 0, finals="WC", edition=2018),  # H
        row("m2", date(2018, 1, 2), "a", "b", 1, 1, finals="WC", edition=2018),  # D
        row("m3", date(2018, 1, 3), "a", "b", 0, 3, finals="WC", edition=2018),  # A
        row("m4", date(2020, 1, 1), "a", "b", 5, 0, finals="WC", edition=2020),  # after cutoff
        row("m5", date(2018, 1, 4), "a", "b", 1, 0, tournament="Friendly"),  # not finals
    ]
    path = warehouse(tmp_path, rows)
    pool = score_pool_before(date(2019, 1, 1), path)
    assert pool == {"H": [(2, 0)], "D": [(1, 1)], "A": [(0, 3)]}


def test_bind_match_probs_naive_is_uniform(tmp_path):
    path = warehouse(tmp_path, [])
    probs = bind_match_probs("naive-tournament-v1", small_format(), date(2020, 1, 1), path)
    assert probs("a", "b", None) == (1 / 3, 1 / 3, 1 / 3)
    assert probs("a", "b", "a") == (1 / 3, 1 / 3, 1 / 3)  # naive ignores host, per the spec


def test_bind_match_probs_unknown_model_raises(tmp_path):
    path = warehouse(tmp_path, [])
    with pytest.raises(ValueError, match="unknown model version"):
        bind_match_probs("no-such-model", small_format(), date(2020, 1, 1), path)


def test_eloratings_ratings_for_takes_the_first_match_on_or_after_as_of(tmp_path):
    rows = [
        # a's last match before as_of: not used (its rating would be stale)
        row(
            "m1",
            date(2019, 1, 1),
            "a",
            "x",
            1,
            0,
            elo_home_rating_pre=1500,
            elo_away_rating_pre=1400,
        ),
        # a's first tournament match, on as_of: this rating is used
        row(
            "m2",
            date(2020, 6, 1),
            "a",
            "b",
            1,
            0,
            finals="EURO",
            edition=2020,
            elo_home_rating_pre=1550,
            elo_away_rating_pre=1450,
        ),
    ]
    path = warehouse(tmp_path, rows)
    ratings = eloratings_ratings_for(small_format(), date(2020, 6, 1), path)
    assert ratings["a"] == 1550
    assert ratings["b"] == 1450


def test_predictions_and_save_are_immutable(tmp_path):
    result = Result(
        format_id="euro2020",
        format_version="test-v1",
        seed=0,
        runs=100,
        reach={"a": {"round_of_16": 0.5, "win": 0.1}, "b": {"round_of_16": 0.5, "win": 0.0}},
    )
    as_of = datetime(2020, 6, 10, tzinfo=UTC)
    rows = predictions(result, "national-elo-v1", as_of)
    assert len(rows) == 4
    path = tmp_path / "p.duckdb"
    assert save(rows, "national-elo-v1", path) == 4
    assert save(rows, "national-elo-v1", path) == 0  # rerun: nothing new
    changed = [dataclasses.replace(rows[0], p=0.999), *rows[1:]]
    with pytest.raises(ValueError, match="bump the model version"):
        save(changed, "national-elo-v1", path)


def test_forecast_runs_end_to_end_and_stores_once(tmp_path, monkeypatch):
    """A minimal 4-team, group-only tournament (no knockout), enough finals history for
    national-elo-v1's ordered logit and eloratings-v1's, to check the whole
    bind-pool-simulate-store pipeline, not just its pieces."""
    rows = []
    for i in range(60):
        d = date(2010, 1, 1 + (i % 27))
        home, away = ("a", "b") if i % 2 == 0 else ("c", "d")
        rows.append(
            row(
                f"f{i}",
                d,
                home,
                away,
                2 if i % 3 else 0,
                0 if i % 3 else 2,
                finals="EURO",
                edition=2000 + (i % 4) * 4,
                elo_home_rating_pre=1500 + i,
                elo_away_rating_pre=1500 - i,
            )
        )
    # the tournament's own matches: only their dates matter (first_match_date), teams get
    # their elo rating from here too
    rows.append(
        row(
            "t1",
            date(2020, 6, 11),
            "a",
            "b",
            1,
            0,
            finals="EURO",
            edition=2020,
            elo_home_rating_pre=1600,
            elo_away_rating_pre=1400,
        )
    )
    rows.append(
        row(
            "t2",
            date(2020, 6, 12),
            "c",
            "d",
            1,
            1,
            finals="EURO",
            edition=2020,
            elo_home_rating_pre=1500,
            elo_away_rating_pre=1500,
        )
    )
    warehouse_path = warehouse(tmp_path, rows)
    predictions_path = tmp_path / "p.duckdb"
    fmt = dataclasses.replace(small_format(), id="euro2020", year=2020)

    monkeypatch.setattr(
        "football_forecasting.tournament_run.load_formats", lambda path=None: {"euro2020": fmt}
    )
    result, new = forecast(
        "euro2020", "national-elo-v1", runs=50, warehouse=warehouse_path, path=predictions_path
    )
    assert result.runs == 50
    assert set(result.reach) == {"a", "b", "c", "d"}
    for reach in result.reach.values():
        assert 0 <= reach["win"] <= 1
    assert new == len(predictions(result, "national-elo-v1", datetime.now(tz=UTC)))
