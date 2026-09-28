import dataclasses
import math
from datetime import UTC, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest

from football_forecasting import market_aware
from football_forecasting.backtest import Prediction, run, save
from football_forecasting.data import Fixture, Match, Odds
from football_forecasting.models import (
    DixonColes,
    DixonColesCountry,
    Elo,
    EloCountry,
    MarketConsensus,
    Naive,
    Poisson,
    Row,
    ShotsDixonColes,
    XgDixonColes,
    score_probs,
)
from football_forecasting.report import report

T0 = datetime(2004, 8, 6, tzinfo=UTC)
TEAMS = ["A", "B", "C", "D"]


def season_of(day: int) -> str:
    year = 4 + day // 365
    return f"{year:02d}{year + 1:02d}"


def matches(days: int = 1200) -> list[Match]:
    """Two matches every third day; pre-2019/20 style: close_at = result_at."""
    out = []
    for day in range(0, days, 3):
        for i, (home, away) in enumerate([(0, 1), (2, 3)]):
            h, a = TEAMS[(home + day) % 4], TEAMS[(away + day // 3) % 4]
            if h == a:
                a = TEAMS[(TEAMS.index(h) + 1) % 4]
            date = T0 + timedelta(days=day)
            fixture = Fixture(f"E0_{day}_{i}", "E0", season_of(day), h, a)
            result = "HDA"[(day // 3 + i) % 3]
            end_of_day = date + timedelta(days=1)
            goals = {"H": (2, day % 2), "D": (day % 3, day % 3), "A": (0, 1 + day % 2)}[result]
            out.append(
                Match(fixture, result, goals, date - timedelta(hours=20), end_of_day, end_of_day)
            )
    return out


def odds_for(ms: list[Match]) -> dict[str, list[Odds]]:
    books = [("B365", (0.5, 0.3, 0.2)), ("WH", (0.4, 0.3, 0.3)), ("PS", (0.45, 0.2, 0.35))]
    return {
        m.fixture.match_id: [
            Odds(b, moment, at, True, False, (2.0, 3.4, 4.0), p)
            for b, p in books
            for moment, at in [("pre", m.pre_at), ("close", m.close_at)]
        ]
        + [Odds("Avg", "pre", m.pre_at, True, True, (1, 1, 1), (0.9, 0.05, 0.05))]
        for m in ms
    }


def all_models():
    return [Naive(), Elo(), MarketConsensus(), Poisson(), DixonColes()]


class Spy:
    version = "spy"
    params: dict[str, float | str] = {}  # noqa: RUF012

    def __init__(self) -> None:
        self.seen: dict[str, datetime] = {}
        self.violations: list[str] = []

    def observe(self, match: Match) -> None:
        self.seen[match.fixture.match_id] = match.result_at

    def predict(self, fixture, horizon, as_of, odds):
        self.violations += [mid for mid, at in self.seen.items() if at >= as_of]
        self.violations += [o.bookmaker for o in odds if o.available_at > as_of]
        return (1 / 3, 1 / 3, 1 / 3)


def test_models_see_only_earlier_results_and_known_odds():
    ms = matches()
    spy = Spy()
    run([spy], ms, odds_for(ms))
    assert spy.seen
    assert spy.violations == []


def test_changing_later_results_leaves_earlier_predictions_alone():
    ms = matches()
    cut = ms[len(ms) // 2].result_at
    flipped = [
        dataclasses.replace(m, result={"H": "A", "D": "H", "A": "D"}[m.result])
        if m.result_at >= cut
        else m
        for m in ms
    ]
    before = [p for p in run(all_models(), ms, odds_for(ms)) if p.prediction_as_of < cut]
    after = [p for p in run(all_models(), flipped, odds_for(ms)) if p.prediction_as_of < cut]
    assert before and before == after


def test_holdout_matches_are_refused():
    m = matches(3)[0]
    holdout = dataclasses.replace(m, fixture=dataclasses.replace(m.fixture, season="2324"))
    with pytest.raises(ValueError, match="holdout"):
        run([Naive()], [holdout], {})


def test_warm_up_is_observed_not_predicted():
    ms = matches()
    predicted = {p.match_id for p in run([Naive()], ms, {})}
    assert all(season_of(int(mid.split("_")[1])) >= "0506" for mid in predicted)


def test_market_consensus_is_median_of_reliable_bookmakers():
    ms = matches(3)
    fixture = ms[0].fixture
    odds = odds_for(ms)[fixture.match_id]
    odds.append(dataclasses.replace(odds[0], bookmaker="X", is_reliable=False, probs=(1, 0, 0)))
    assert MarketConsensus().predict(fixture, "pre", ms[0].pre_at, odds) == pytest.approx(
        (0.45 / 1.05, 0.3 / 1.05, 0.3 / 1.05)
    )


def test_probabilities_sum_to_one():
    ms = matches()
    for p in run(all_models(), ms, odds_for(ms)):
        assert p.p_home + p.p_draw + p.p_away == pytest.approx(1)
        assert min(p.p_home, p.p_draw, p.p_away) > 0


def test_stored_predictions_never_change(tmp_path):
    ms = matches()
    models = [Naive()]
    predictions = run(models, ms, {})
    path = tmp_path / "p.duckdb"
    assert save(predictions, models, "0405..0708", path) == len(predictions)
    assert save(predictions, models, "0405..0708", path) == 0
    changed = [dataclasses.replace(predictions[0], p_home=0.9), *predictions[1:]]
    with pytest.raises(ValueError, match="bump the model version"):
        save(changed, models, "0405..0708", path)


def test_every_run_is_recorded(tmp_path):
    ms = matches()
    models = [Naive(), Elo(k=30)]
    predictions = run(models, ms, {})
    path = tmp_path / "p.duckdb"
    save(predictions, models, "0405..0708", path)
    save(predictions, models, "0405..0708", path)
    con = duckdb.connect(str(path))
    runs = con.execute(
        """
        select model_version, params, predictions, new_predictions
        from runs order by started_at, model_version
        """
    ).fetchall()
    n = len(predictions) // 2
    assert runs == [
        ("elo-v1", '{"k": 30, "home_advantage": 60, "promoted_rating": 1400}', n, n),
        ("naive-v1", "{}", n, n),
        ("elo-v1", '{"k": 30, "home_advantage": 60, "promoted_rating": 1400}', n, 0),
        ("naive-v1", "{}", n, 0),
    ]
    # predictions keep the run that first stored them
    stored_by = con.execute(
        """
        select distinct p.run_id = r.run_id from predictions as p
        cross join (select run_id from runs order by started_at limit 1) as r
        """
    ).fetchall()
    assert stored_by == [(True,)]


def test_scores(tmp_path):
    warehouse = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(warehouse))
    con.execute(
        """
        create table int_matches as select * from (values
            ('m1', 'E0', '0506', 'H', false), ('m2', 'E0', '1920', 'A', true)
        ) as t(match_id, league, season, result, pre_timing_uncertain)
        """
    )
    con.close()
    at = datetime(2020, 1, 1, tzinfo=UTC)
    predictions = [
        ("m1", "pre", 0.5, 0.3, 0.2),
        ("m2", "pre", 0.5, 0.3, 0.2),
        ("m2", "close", 0.2, 0.3, 0.5),
    ]
    path = tmp_path / "p.duckdb"
    rows = [Prediction(m + h, m, h, at, "x", *p, *[None] * 3) for m, h, *p in predictions]
    save(rows, [], "0506..1920", path)
    text = report(path, ("x",), warehouse)
    # m1: log loss -ln 0.5, Brier 0.25 + 0.09 + 0.04, RPS ((0.5 - 1)^2 + 0.2^2) / 2
    assert f"| development | pre | x | 1 | {-math.log(0.5):.4f} | 0.3800 | 0.1450 |" in text
    # m2 close: -ln 0.5, RPS (0.2^2 + 0.5^2) / 2; m2 pre is uncertain
    assert f"| validation | close | x | 1 | {-math.log(0.5):.4f} | 0.3800 | 0.1450 |" in text
    assert text.count("| validation | pre |") == 1


def test_score_grid():
    # independent Poisson with equal rates: home and away wins equally likely
    h, d, a = score_probs(1.3, 1.3, 0.0)
    assert h == pytest.approx(a)
    # negative rho moves probability to 0-0 and 1-1, so to draws
    assert score_probs(1.3, 1.3, -0.1)[1] > d


def test_goal_models_learn_team_strength():
    ms = matches()
    strong = [
        dataclasses.replace(m, result="H", goals=(3, 0)) if m.fixture.home_team == "A" else m
        for m in ms
    ]
    for model in (Poisson(), DixonColes()):
        run([model], strong, {})
        last = next(m for m in reversed(strong) if m.fixture.home_team == "A")
        p = model.predict(last.fixture, "pre", last.pre_at, [])
        assert p is not None and p[0] > 0.6


LEAGUES = {"E0": ("England", 1), "E1": ("England", 2)}


def two_leagues() -> list[Match]:
    """2004/05: E0 W X Y Z, E1 A B C D, A wins every match 3-0. 2005/06: A
    promoted in place of Z, which drops to E1 beside N, new from below."""
    out = []
    seasons = [("0405", {"E0": "WXYZ", "E1": "ABCD"}), ("0506", {"E0": "WXYA", "E1": "ZBCN"})]
    for year, (season, lineup) in enumerate(seasons):
        for rnd in range(12):
            date = T0 + timedelta(days=365 * year + 3 * rnd)
            for league, teams in lineup.items():
                for i, (h, a) in enumerate(
                    [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)][rnd % 6 : rnd % 6 + 1]
                ):
                    home, away = teams[(h + rnd) % 4], teams[(a + rnd) % 4]
                    goals = (3, 0) if home == "A" else (0, 3) if away == "A" else (1, 1)
                    result = "H" if goals[0] > goals[1] else "A" if goals[0] < goals[1] else "D"
                    fixture = Fixture(f"{league}_{season}_{rnd}_{i}", league, season, home, away)
                    end = date + timedelta(days=1)
                    out.append(Match(fixture, result, goals, date - timedelta(hours=20), end, end))
    return out


def test_country_models_carry_teams_across_leagues():
    ms = two_leagues()
    first = [m for m in ms if m.fixture.season == "0405"]
    elo = EloCountry(LEAGUES)
    run([elo], first, {})
    carried = elo.ratings["England", "A"]
    e1_mean = sum(elo.ratings["England", t] for t in "ABCD") / 4
    assert carried > 1400  # started at 1400 in E1 (tier 2) and won every match
    promoted = Fixture("x", "E0", "0506", "A", "W")
    assert elo.rating(promoted, "A") == carried
    assert elo.rating(Fixture("y", "E1", "0506", "N", "B"), "N") == pytest.approx(e1_mean - 100)

    country, plain = DixonColesCountry(LEAGUES), DixonColes()
    run([country, plain], first, {})
    at = ms[-1].pre_at
    p_country = country.predict(promoted, "pre", at, [])
    p_plain = plain.predict(promoted, "pre", at, [])
    assert p_country is not None and p_plain is not None
    assert p_country[0] > p_plain[0]  # A keeps its strength instead of the promoted prior


def test_counts_blend_goals_with_shots_or_xg():
    rows: list[Row] = [
        ("0506", "A", "B", 2, 0, 0.0, (5, 3), (1.5, 0.5)),
        ("0506", "B", "A", 1, 1, 1.0, (3, 5), (0.5, 2.5)),
        ("0506", "A", "B", 3, 1, 2.0, None, None),
    ]
    # goals per shot on target over the rows that have them: 4 / 16
    home, away = ShotsDixonColes(1.0).counts(rows)
    assert list(home) == [1.25, 0.75, 3.0] and list(away) == [0.75, 1.25, 1.0]
    home, _ = ShotsDixonColes(0.5).counts(rows)
    assert list(home) == [1.625, 0.875, 3.0]
    # w = 0 reproduces dixon-coles-v1
    ms = matches(800)
    ms = [dataclasses.replace(m, shots_on_target=(4, 2)) for m in ms]
    shots, dc = ShotsDixonColes(0.0), DixonColes()
    a, b = run([shots], ms, {}), run([dc], ms, {})
    assert [p.p_home for p in a] == pytest.approx([p.p_home for p in b])
    home, away = XgDixonColes(0.5).counts(rows)
    assert list(home) == [1.75, 0.75, 3.0] and list(away) == [0.25, 1.75, 1.0]


def test_market_aware_fit_recovers_weights():
    rng = np.random.default_rng(1)
    market = np.log(rng.dirichlet([4, 2, 3], 20000))
    model = np.log(rng.dirichlet([4, 2, 3], 20000))
    truth = np.array([1.1, 0.3, 0.1, -0.05])
    p = market_aware.probs(truth, market, model)
    y = (rng.random(len(p))[:, None] > p.cumsum(axis=1)).sum(axis=1)
    assert market_aware.fit(market, model, y) == pytest.approx(truth, abs=0.06)


def test_market_aware_uses_only_earlier_seasons():
    rng = np.random.default_rng(2)
    n = 300
    df = pd.DataFrame(
        {
            "horizon": "pre",
            "season": np.repeat(["0506", "0607", "0708"], n // 3),
            "result": rng.choice(list("HDA"), n),
        }
    )
    df[["p_home", "p_draw", "p_away"]] = rng.dirichlet([4, 2, 3], n)
    df[["model_home", "model_draw", "model_away"]] = rng.dirichlet([4, 2, 3], n)
    out, weights = market_aware.walk_forward(df)
    assert sorted(out["season"].unique()) == ["0607", "0708"]
    assert list(weights["n_fit"]) == [100, 200]
    later = df.assign(result=np.where(df["season"] == "0708", "H", df["result"]))
    before = out[out["season"] == "0607"]
    assert before.equals(market_aware.walk_forward(later)[0].query("season == '0607'"))
