"""Walk-forward backtest.

Walks one stream of events in time order: a prediction for each match and
horizon at its prediction time, and each result at its result_at. At equal
times predictions go first, so a model only ever sees results with
result_at strictly before the prediction time. Before 2019/20 the `close` time
is the end of match day, the same as result_at, so no result from that day
reaches a `close` prediction. Odds of the predicted match reach the model when
available_at <= the prediction time. Models get nothing else.
"""

import csv
import hashlib
import tempfile
from dataclasses import astuple, dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from football_forecasting.data import (
    FIRST_DEVELOPMENT_SEASON,
    FIRST_HOLDOUT_SEASON,
    PREDICTIONS,
    Match,
    Odds,
    load,
)
from football_forecasting.models import Elo, MarketConsensus, Model, Naive
from football_forecasting.report import report

HORIZONS = ("pre", "close")
EXECUTABLE_BOOKMAKER = "B365"  # docs/experiment-spec.md, Betting rule


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    match_id: str
    horizon: str
    prediction_as_of: datetime
    model_version: str
    p_home: float
    p_draw: float
    p_away: float
    # bet365 odds of the horizon's moment, known at prediction_as_of
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None


def run(models: list[Model], matches: list[Match], odds: dict[str, list[Odds]]) -> list[Prediction]:
    """Predict every development and validation match at both horizons."""
    events: list[tuple[datetime, int, str, Match, str]] = []
    for m in matches:
        if m.fixture.season >= FIRST_HOLDOUT_SEASON:
            raise ValueError(f"holdout match {m.fixture.match_id} passed to the backtest")
        if m.fixture.season >= FIRST_DEVELOPMENT_SEASON:
            events.append((m.pre_at, 0, m.fixture.match_id, m, "pre"))
            events.append((m.close_at, 0, m.fixture.match_id, m, "close"))
        events.append((m.result_at, 1, m.fixture.match_id, m, ""))
    events.sort(key=lambda e: e[:3])

    predictions = []
    for as_of, kind, match_id, m, horizon in events:
        if kind == 1:
            for model in models:
                model.observe(m.fixture, m.result)
            continue
        known = [o for o in odds.get(match_id, []) if o.available_at <= as_of]
        executable = next(
            (o for o in known if o.bookmaker == EXECUTABLE_BOOKMAKER and o.moment == horizon), None
        )
        odds_home, odds_draw, odds_away = executable.odds if executable else (None, None, None)
        for model in models:
            probs = model.predict(m.fixture, horizon, as_of, known)
            if probs is None:
                continue
            key = f"{model.version}|{horizon}|{match_id}"
            predictions.append(
                Prediction(
                    hashlib.sha256(key.encode()).hexdigest()[:16],
                    match_id,
                    horizon,
                    as_of,
                    model.version,
                    float(probs[0]),
                    float(probs[1]),
                    float(probs[2]),
                    odds_home,
                    odds_draw,
                    odds_away,
                )
            )
    return predictions


def save(predictions: list[Prediction], path: Path = PREDICTIONS) -> int:
    """Append predictions not yet stored; return how many were new.

    Stored predictions never change. A rerun that gives a different number for
    a stored prediction fails: change the model's version instead."""
    con = duckdb.connect(str(path))
    con.execute(
        """
        create table if not exists predictions (
            prediction_id varchar primary key,
            match_id varchar not null,
            horizon varchar not null,
            prediction_as_of timestamptz not null,
            model_version varchar not null,
            p_home double not null,
            p_draw double not null,
            p_away double not null,
            odds_home double,
            odds_draw double,
            odds_away double,
            stored_at timestamptz not null default current_timestamp
        )
        """
    )
    columns = list(Prediction.__dataclass_fields__)
    # through a CSV file: binding Python lists as parameters is ~100x slower
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="") as f:
        csv.writer(f).writerows(astuple(p) for p in predictions)
        f.flush()
        con.execute("create temp table incoming as from predictions limit 0")
        con.execute(f"copy incoming ({', '.join(columns)}) from '{f.name}' (header false)")
    changed = con.execute(
        f"""
        select count(*) from incoming as i
        inner join predictions as p using (prediction_id)
        where ({", ".join(f"i.{c}" for c in columns)})
            is distinct from ({", ".join(f"p.{c}" for c in columns)})
        """
    ).fetchone()
    if changed and changed[0]:
        raise ValueError(f"{changed[0]} stored predictions would change; bump the model version")
    new = con.execute(
        f"""
        insert into predictions ({", ".join(columns)})
        select {", ".join(columns)} from incoming
        where prediction_id not in (select prediction_id from predictions)
        """
    ).fetchone()
    con.close()
    return new[0] if new else 0


def main() -> None:
    matches, odds = load()
    predictions = run([Naive(), MarketConsensus(), Elo()], matches, odds)
    print(f"{len(predictions)} predictions, {save(predictions)} new\n")
    print(report())


if __name__ == "__main__":
    main()
