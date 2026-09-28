import dataclasses
import math
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from football_forecasting.backtest import Prediction, run, save
from football_forecasting.data import Fixture, Match, Odds
from football_forecasting.models import Elo, MarketConsensus, Naive
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
            out.append(Match(fixture, result, date - timedelta(hours=20), end_of_day, end_of_day))
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
    return [Naive(), Elo(), MarketConsensus()]


class Spy:
    version = "spy"

    def __init__(self) -> None:
        self.seen: dict[str, datetime] = {}
        self.by_id: dict[str, Match] = {}
        self.violations: list[str] = []

    def observe(self, fixture: Fixture, result: str) -> None:
        self.seen[fixture.match_id] = self.by_id[fixture.match_id].result_at

    def predict(self, fixture, horizon, as_of, odds):
        self.violations += [mid for mid, at in self.seen.items() if at >= as_of]
        self.violations += [o.bookmaker for o in odds if o.available_at > as_of]
        return (1 / 3, 1 / 3, 1 / 3)


def test_models_see_only_earlier_results_and_known_odds():
    ms = matches()
    spy = Spy()
    spy.by_id = {m.fixture.match_id: m for m in ms}
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
    predictions = run([Naive()], ms, {})
    path = tmp_path / "p.duckdb"
    assert save(predictions, path) == len(predictions)
    assert save(predictions, path) == 0
    changed = [dataclasses.replace(predictions[0], p_home=0.9), *predictions[1:]]
    with pytest.raises(ValueError, match="bump the model version"):
        save(changed, path)


def test_scores(tmp_path):
    warehouse = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(warehouse))
    con.execute(
        """
        create table int_matches as select * from (values
            ('m1', '0506', 'H', false), ('m2', '1920', 'A', true)
        ) as t(match_id, season, result, pre_timing_uncertain)
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
    save([Prediction(m + h, m, h, at, "x", *p, *[None] * 3) for m, h, *p in predictions], path)
    text = report(path, ("x",), warehouse)
    # m1: log loss -ln 0.5, Brier 0.25 + 0.09 + 0.04, RPS ((0.5 - 1)^2 + 0.2^2) / 2
    assert f"| development | pre | x | 1 | {-math.log(0.5):.4f} | 0.3800 | 0.1450 |" in text
    # m2 close: -ln 0.5, RPS (0.2^2 + 0.5^2) / 2; m2 pre is uncertain
    assert f"| validation | close | x | 1 | {-math.log(0.5):.4f} | 0.3800 | 0.1450 |" in text
    assert text.count("| validation | pre |") == 1
