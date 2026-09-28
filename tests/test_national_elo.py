import dataclasses
from datetime import date
from pathlib import Path

import duckdb
import pytest

from football_forecasting import national_elo as ne
from football_forecasting import national_elo_backtest as neb

COLUMNS = """
    match_id varchar, match_date date, home_team_id varchar, away_team_id varchar,
    home_score integer, away_score integer, home_score_90 integer, away_score_90 integer,
    score_90_reliable boolean, neutral boolean, awarded boolean, tournament varchar,
    finals varchar, edition integer, elo_home_rating_pre integer, elo_away_rating_pre integer
"""


def make_match(
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
    score_90_reliable: bool = True,
    home_score_90: int | None = None,
    away_score_90: int | None = None,
    awarded: bool = False,
    elo_home_rating_pre: int | None = None,
    elo_away_rating_pre: int | None = None,
) -> ne.NationalMatch:
    return ne.NationalMatch(
        match_id,
        match_date,
        home,
        away,
        home_score,
        away_score,
        home_score_90 if home_score_90 is not None else (home_score if score_90_reliable else None),
        away_score_90 if away_score_90 is not None else (away_score if score_90_reliable else None),
        score_90_reliable,
        neutral,
        awarded,
        tournament,
        finals,
        edition,
        elo_home_rating_pre,
        elo_away_rating_pre,
    )


def warehouse(tmp_path: Path, matches: list[ne.NationalMatch]) -> Path:
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute(f"create table int_international_matches ({COLUMNS})")
    con.executemany(
        "insert into int_international_matches values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [dataclasses.astuple(m) for m in matches],
    )
    con.close()
    return path


def test_match_weight_categories():
    assert ne.match_weight("FIFA World Cup") == 60
    assert ne.match_weight("UEFA Euro") == 50
    assert ne.match_weight("Copa América") == 50
    assert ne.match_weight("FIFA World Cup qualification") == 40
    assert ne.match_weight("UEFA Nations League") == 40
    assert ne.match_weight("Friendly") == 20
    assert ne.match_weight("CECAFA Cup") == 30  # everything else


def test_goal_multiplier():
    assert ne.goal_multiplier(0) == 1
    assert ne.goal_multiplier(1) == 1
    assert ne.goal_multiplier(-1) == 1
    assert ne.goal_multiplier(2) == 1.5
    assert ne.goal_multiplier(3) == pytest.approx(14 / 8)
    assert ne.goal_multiplier(10) == pytest.approx(21 / 8)


def test_home_advantage_only_when_not_neutral():
    windows: list[tuple[date, date]] = []
    home_game = ne.NationalElo(windows)
    neutral_game = ne.NationalElo(windows)
    assert home_game.difference("A", "B", "A") == pytest.approx(100.0)
    assert neutral_game.difference("A", "B", None) == pytest.approx(0.0)
    # home advantage can sit with either side, by which team_id is passed as home
    assert home_game.difference("A", "B", "B") == pytest.approx(-100.0)


def test_observe_updates_both_teams_and_skips_awarded():
    model = ne.NationalElo([])
    a0, b0 = model.rating("A"), model.rating("B")
    m = make_match("m1", date(2000, 1, 1), "A", "B", 2, 0, neutral=True, score_90_reliable=False)
    model.observe(m)
    assert model.rating("A") > a0
    assert model.rating("B") < b0
    assert model.rating("A") - a0 == pytest.approx(b0 - model.rating("B"))

    before_a, before_b = model.rating("A"), model.rating("B")
    awarded = make_match(
        "m2", date(2000, 1, 2), "A", "B", 3, 0, neutral=True, awarded=True, score_90_reliable=False
    )
    model.observe(awarded)
    assert model.rating("A") == before_a
    assert model.rating("B") == before_b


def test_tournament_windows():
    matches = [
        make_match("m1", date(2006, 6, 1), "A", "B", 1, 0, finals="WC", edition=2006),
        make_match("m2", date(2006, 7, 1), "C", "D", 0, 0, finals="WC", edition=2006),
        make_match("m3", date(2008, 6, 1), "A", "C", 2, 1, finals="EURO", edition=2008),
    ]
    windows = ne.tournament_windows(matches)
    assert sorted(windows) == [
        (date(2006, 6, 1), date(2006, 7, 1)),
        (date(2008, 6, 1), date(2008, 6, 1)),
    ]


def test_tournament_logit_does_not_leak_within_a_tournament():
    windows = [(date(2006, 6, 1), date(2006, 6, 20))]
    logit = ne.TournamentLogit(windows)
    # warm-up history: clean separation by outcome, so a real fit is possible
    for i in range(30):
        logit.add(date(2000, 1, i % 27 + 1), 200.0, 0)  # 'H'
        logit.add(date(2000, 1, i % 27 + 1), -200.0, 2)  # 'A'
        logit.add(date(2000, 1, i % 27 + 1), 0.0, 1)  # 'D'
    p_before = logit.predict(date(2006, 6, 1), 100.0)
    assert p_before is not None
    fit_after_first_call = logit.params
    assert fit_after_first_call is not None
    # a later match of the SAME tournament must not refit on its own earlier games
    logit.add(date(2006, 6, 5), 900.0, 2)  # a wild, wrong-signed result if it leaked in
    p_mid_tournament = logit.predict(date(2006, 6, 15), 100.0)
    assert p_mid_tournament == p_before
    fit_mid_tournament = logit.params
    assert fit_mid_tournament is not None
    assert (fit_mid_tournament == fit_after_first_call).all()
    assert logit.cutoff == date(2006, 6, 1)
    # the next tournament refits, now including that result
    logit.predict(date(2007, 1, 1), 100.0)
    assert logit.cutoff == date(2007, 1, 1)
    fit_next_tournament = logit.params
    assert fit_next_tournament is not None
    assert not (fit_next_tournament == fit_after_first_call).all()


def test_naive_tournament_benchmark_splits_by_host():
    naive = ne.NaiveTournamentBenchmark()
    host_win = make_match(
        "m1", date(2006, 1, 1), "A", "B", 2, 0, neutral=False, finals="WC", edition=2006
    )
    away_win = make_match(
        "m2", date(2006, 1, 2), "C", "D", 0, 1, neutral=True, finals="WC", edition=2006
    )
    naive.observe(host_win)
    naive.observe(away_win)
    assert naive.predict(neutral=False) == (1.0, 0.0, 0.0)
    assert naive.predict(neutral=True) == (0.0, 0.0, 1.0)
    assert naive.predict(neutral=False) != naive.predict(neutral=True)


def test_eloratings_benchmark_needs_both_ratings():
    bench = ne.EloRatingsBenchmark([])
    missing = make_match(
        "m1", date(2006, 1, 1), "A", "B", 1, 0, finals="WC", edition=2006, elo_home_rating_pre=None
    )
    assert bench.predict(missing) is None
    bench.observe(missing)  # must not raise even without ratings


def test_load_respects_before_cutoff(tmp_path):
    matches = [
        make_match("m1", date(2019, 12, 31), "A", "B", 1, 0),
        make_match("m2", date(2020, 1, 1), "A", "B", 1, 0),
    ]
    path = warehouse(tmp_path, matches)
    loaded = ne.load(path, before=date(2020, 1, 1))
    assert [m.match_id for m in loaded] == ["m1"]


def test_load_default_stops_before_validation(tmp_path):
    matches = [
        make_match("m1", date(2019, 12, 31), "A", "B", 1, 0),
        make_match("m2", date(2020, 1, 1), "A", "B", 1, 0),
    ]
    path = warehouse(tmp_path, matches)
    assert [m.match_id for m in ne.load(path)] == ["m1"]


def test_match_probs_orders_team_a_as_home_and_caches(tmp_path):
    ne._built.cache_clear()
    matches = []
    for i in range(40):
        d = date(2000, 1, 1 + (i % 27))
        matches.append(make_match(f"f{i}", d, "A", "B", 2, 0, finals="WC", edition=2000))
        matches.append(make_match(f"g{i}", d, "B", "A", 0, 2, finals="WC", edition=2000))
    path = warehouse(tmp_path, matches)
    as_of = date(2010, 1, 1)
    # A is far stronger than B by 2010; giving A the home edge should favor it heavily
    p = ne.match_probs("A", "B", "A", as_of, path)
    assert p is not None and p[0] > 0.9 > p[2]
    # swap team_a/team_b but keep the same physical team ("A") at home: now team_a
    # is the weak, away side, so the output slots swap around
    q = ne.match_probs("B", "A", "A", as_of, path)
    assert q is not None and q[2] > 0.9 > q[0]
    assert ne._built.cache_info().hits >= 1  # second call for the same as_of reused the build


def test_should_score_development_reliable_non_friendly():
    in_scope = make_match(
        "m1", date(2010, 1, 1), "A", "B", 1, 0, tournament="FIFA World Cup qualification"
    )
    friendly = make_match("m2", date(2010, 1, 1), "A", "B", 1, 0, tournament="Friendly")
    unreliable = make_match("m3", date(2010, 1, 1), "A", "B", 1, 0, score_90_reliable=False)
    too_early = make_match("m4", date(2000, 1, 1), "A", "B", 1, 0, tournament="FIFA World Cup")
    too_late = make_match("m5", date(2020, 1, 1), "A", "B", 1, 0, tournament="FIFA World Cup")
    assert neb.should_score(in_scope)
    assert not neb.should_score(friendly)
    assert not neb.should_score(unreliable)
    assert not neb.should_score(too_early)
    assert not neb.should_score(too_late)


def test_run_accepts_validation_matches():
    validation_era = make_match("m1", date(2020, 1, 1), "A", "B", 1, 0)
    neb.run([validation_era])  # does not raise


def test_run_refuses_holdout_or_later_matches():
    holdout_era = make_match("m1", date(2024, 7, 15), "A", "B", 1, 0)
    with pytest.raises(ValueError, match="holdout"):
        neb.run([holdout_era])


def test_run_with_should_score_validation_only_scores_validation_finals():
    dev_finals = make_match(
        "d1",
        date(2018, 6, 1),
        "A",
        "B",
        1,
        0,
        finals="WC",
        edition=2018,
        tournament="FIFA World Cup",
    )
    validation_finals = make_match(
        "v1",
        date(2020, 6, 1),
        "A",
        "B",
        1,
        0,
        finals="EURO",
        edition=2020,
        tournament="UEFA Euro",
    )
    validation_competitive = make_match(
        "v2", date(2020, 6, 2), "A", "B", 1, 0, tournament="FIFA World Cup qualification"
    )
    preds, _ = neb.run(
        [dev_finals, validation_finals, validation_competitive],
        should_score=neb.should_score_validation,
    )
    scored_ids = {p.match_id for p in preds["national-elo-v1"]}
    assert scored_ids == {"v1"}  # not the development match, not the wider validation set


def test_confirm_counts_never_reads_row_detail(tmp_path):
    matches = [
        make_match("m1", date(2019, 12, 31), "A", "B", 1, 0, finals="WC", edition=2018),  # dev
        make_match("m2", date(2020, 1, 1), "A", "B", 1, 0, finals="WC", edition=2020),  # validation
        make_match(
            "m3", date(2024, 7, 14), "A", "B", 1, 0, finals="EURO", edition=2024
        ),  # validation
        make_match("m4", date(2024, 7, 15), "A", "B", 1, 0, finals="WC", edition=2026),  # holdout
    ]
    path = warehouse(tmp_path, matches)
    text = neb.confirm_counts(path)
    assert "validation finals matches: 2" in text
    assert "holdout finals matches: 1" in text


def test_stored_predictions_never_change(tmp_path):
    matches = [
        make_match(
            f"m{i}",
            date(2010, 1, 1 + i),
            "A",
            "B",
            i % 3,
            0,
            finals="WC",
            edition=2010,
            tournament="FIFA World Cup",
        )
        for i in range(5)
    ]
    preds, models = neb.run(matches)
    path = tmp_path / "p.duckdb"
    rows = preds["naive-tournament-v1"]
    assert rows
    assert neb.save(rows, [models["naive-tournament-v1"]], "0000..0000", path) == len(rows)
    assert neb.save(rows, [models["naive-tournament-v1"]], "0000..0000", path) == 0
    changed = [dataclasses.replace(rows[0], p_home=0.999), *rows[1:]]
    with pytest.raises(ValueError, match="bump the model version"):
        neb.save(changed, [models["naive-tournament-v1"]], "0000..0000", path)


def test_scores_intersects_models_and_filters_tournament_only():
    tournament = make_match(
        "t1",
        date(2010, 1, 1),
        "A",
        "B",
        1,
        0,
        finals="WC",
        edition=2010,
        tournament="FIFA World Cup",
    )
    competitive = make_match(
        "c1", date(2010, 1, 2), "A", "B", 0, 0, tournament="FIFA World Cup qualification"
    )
    by_id = {"t1": tournament, "c1": competitive}
    both = {
        "national-elo-v1": [
            neb._prediction("national-elo-v1", tournament, (0.5, 0.3, 0.2)),
            neb._prediction("national-elo-v1", competitive, (0.4, 0.3, 0.3)),
        ],
        "naive-tournament-v1": [
            neb._prediction("naive-tournament-v1", tournament, (0.4, 0.3, 0.3)),
            neb._prediction("naive-tournament-v1", competitive, (0.4, 0.3, 0.3)),
        ],
    }
    ids, _days, _sc = neb.scores(both, by_id, tournament_only=True)
    assert ids == ["t1"]
    ids_all, _, _ = neb.scores(both, by_id, tournament_only=False)
    assert ids_all == ["t1", "c1"]
