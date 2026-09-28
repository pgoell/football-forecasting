"""Links a model to the tournament simulator and stores its forecast
(docs/tournament-spec.md, Simulator; Rules against fooling ourselves).

`simulate()` (tournament.py) wants a 3-arg `match_probs(team_a, team_b, home_team_or_none)`
and a `score_pool` of historical (goals_a, goals_b) by outcome, for one tournament. This
module binds each of the three models we forecast tournaments with (national-elo-v1,
eloratings-v1, naive-tournament-v1) to that interface at one `as_of` (the day before the
tournament's first match, so every match up to it is known: docs/tournament-spec.md,
Targets, Tournament horizon), and stores the per-team, per-round result immutably.
"""

import csv
import hashlib
import tempfile
import uuid
from dataclasses import astuple, dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import duckdb

from football_forecasting.backtest import git_state
from football_forecasting.data import PREDICTIONS, WAREHOUSE
from football_forecasting.national_elo import eloratings_benchmark_at, outcome
from football_forecasting.national_elo import match_probs as national_elo_match_probs
from football_forecasting.tournament import (
    Format,
    MatchProbs,
    Probs,
    Result,
    ScorePool,
    load_formats,
    simulate,
)

MODEL_VERSIONS = ("national-elo-v1", "eloratings-v1", "naive-tournament-v1")
# EURO 2020 (played 2021), WC 2022, EURO 2024: docs/tournament-spec.md, Data periods.
VALIDATION_TOURNAMENTS = ("euro2020", "wc2022", "euro2024")


def first_match_date(kind: str, year: int, warehouse: Path = WAREHOUSE) -> date:
    """The earliest real match of this finals tournament (`int_international_matches.finals`
    is 'WC' or 'EURO'; `edition` is the year, 2020 for EURO 2020 though it was played in
    2021: dbt/models/staging/stg_international_results__matches.sql)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    row = con.execute(
        "select min(match_date) from int_international_matches where finals = ? and edition = ?",
        [kind, year],
    ).fetchone()
    con.close()
    if row is None or row[0] is None:
        raise ValueError(f"no matches found for {kind} {year}")
    return row[0]


def score_pool_before(as_of: date, warehouse: Path = WAREHOUSE) -> ScorePool:
    """H/D/A pools of real 90-minute scores from every earlier WC/EURO finals match with a
    reliable one (docs/tournament-spec.md, Simulator: the model gives H/D/A, group
    tie-breaks need a score, so each run draws one from history by outcome)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select home_score_90, away_score_90
        from int_international_matches
        where finals is not null and score_90_reliable and match_date < ?
        """,
        [as_of],
    ).fetchall()
    con.close()
    pool: dict[str, list[tuple[int, int]]] = {"H": [], "D": [], "A": []}
    for home_goals, away_goals in rows:
        pool[outcome(home_goals, away_goals)].append((home_goals, away_goals))
    return pool


def eloratings_ratings_for(
    fmt: Format, as_of: date, warehouse: Path = WAREHOUSE
) -> dict[str, float]:
    """Each of the tournament's teams' own eloratings.net rating entering it: the pre-match
    rating of its own earliest real match on or after `as_of`, so no result of that match or
    a later one leaks in (usually the tournament's own first match for that team)."""
    teams = [team for group in fmt.groups.values() for team in group] if fmt.groups else []
    placeholders = ",".join("?" * len(teams))
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        f"""
        select home_team_id, away_team_id, elo_home_rating_pre, elo_away_rating_pre
        from int_international_matches
        where match_date >= ?
            and (home_team_id in ({placeholders}) or away_team_id in ({placeholders}))
        order by match_date
        """,
        [as_of, *teams, *teams],
    ).fetchall()
    con.close()
    ratings: dict[str, float] = {}
    for home, away, home_rating, away_rating in rows:
        if home in teams and home not in ratings and home_rating is not None:
            ratings[home] = home_rating
        if away in teams and away not in ratings and away_rating is not None:
            ratings[away] = away_rating
    return ratings


def bind_match_probs(
    model_version: str, fmt: Format, as_of: date, warehouse: Path = WAREHOUSE
) -> MatchProbs:
    """`model_version`'s match_probs, bound to `as_of`, as the simulator's 3-arg interface."""
    if model_version == "national-elo-v1":

        def national_elo_probs(a: str, b: str, home: str | None) -> Probs:
            p = national_elo_match_probs(a, b, home, as_of, warehouse)
            assert p is not None
            return p

        return national_elo_probs
    if model_version == "eloratings-v1":
        bench = eloratings_benchmark_at(as_of, warehouse)
        ratings = eloratings_ratings_for(fmt, as_of, warehouse)

        def eloratings_probs(a: str, b: str, home: str | None) -> Probs:
            bonus = (
                bench.home_advantage if home == a else -bench.home_advantage if home == b else 0.0
            )
            p = bench.logit.predict(as_of, ratings[a] - ratings[b] + bonus)
            assert p is not None
            return p

        return eloratings_probs
    if model_version == "naive-tournament-v1":
        # Every team equally likely under the format (docs/tournament-spec.md, Benchmarks):
        # a uniform match model, run through the same simulator, gives exactly that by the
        # format's own symmetry, no host split (unlike the match-level naive benchmark).
        return lambda a, b, home: (1 / 3, 1 / 3, 1 / 3)
    raise ValueError(f"unknown model version: {model_version}")


@dataclass(frozen=True)
class TournamentPrediction:
    prediction_id: str
    tournament: str
    team: str
    round: str
    p: float
    runs: int
    seed: int
    format_version: str
    model_version: str
    prediction_as_of: datetime


def predictions(
    result: Result, model_version: str, prediction_as_of: datetime
) -> list[TournamentPrediction]:
    rows = []
    for team, reach in result.reach.items():
        for round_name, p in reach.items():
            key = f"{model_version}|{result.format_id}|{team}|{round_name}|{result.seed}"
            rows.append(
                TournamentPrediction(
                    hashlib.sha256(key.encode()).hexdigest()[:16],
                    result.format_id,
                    team,
                    round_name,
                    float(p),
                    result.runs,
                    result.seed,
                    result.format_version,
                    model_version,
                    prediction_as_of,
                )
            )
    return rows


def save(rows: list[TournamentPrediction], model_version: str, path: Path = PREDICTIONS) -> int:
    """Record the run and append predictions not yet stored; return how many were new.
    Same immutability as `backtest.save`/`national_elo_backtest.save`: stored predictions
    never change, a rerun stores nothing new (docs/tournament-spec.md, Rules against
    fooling ourselves)."""
    con = duckdb.connect(str(path))
    con.execute(
        """
        create table if not exists tournament_runs (
            run_id varchar not null,
            model_version varchar not null,
            started_at timestamptz not null,
            git_sha varchar not null,
            git_dirty boolean not null,
            tournament varchar not null,
            predictions integer not null,
            new_predictions integer not null,
            primary key (run_id, model_version, tournament)
        )
        """
    )
    con.execute(
        """
        create table if not exists tournament_predictions (
            prediction_id varchar primary key,
            tournament varchar not null,
            team varchar not null,
            round varchar not null,
            p double not null,
            runs integer not null,
            seed integer not null,
            format_version varchar not null,
            model_version varchar not null,
            prediction_as_of timestamptz not null,
            stored_at timestamptz not null default current_timestamp,
            run_id varchar not null
        )
        """
    )
    columns = list(TournamentPrediction.__dataclass_fields__)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="") as f:
        csv.writer(f).writerows(astuple(p) for p in rows)
        f.flush()
        con.execute("create temp table incoming as from tournament_predictions limit 0")
        con.execute(f"copy incoming ({', '.join(columns)}) from '{f.name}' (header false)")
    changed = con.execute(
        f"""
        select count(*) from incoming as i
        inner join tournament_predictions as p using (prediction_id)
        where ({", ".join(f"i.{c}" for c in columns)})
            is distinct from ({", ".join(f"p.{c}" for c in columns)})
        """
    ).fetchone()
    if changed and changed[0]:
        raise ValueError(f"{changed[0]} stored predictions would change; bump the model version")
    run_id = uuid.uuid4().hex[:12]
    sha, dirty = git_state()
    tournament = rows[0].tournament if rows else ""
    con.execute("begin")
    con.execute(
        f"""
        insert into tournament_predictions ({", ".join(columns)}, run_id)
        select {", ".join(columns)}, $run_id from incoming
        where prediction_id not in (select prediction_id from tournament_predictions)
        """,
        {"run_id": run_id},
    )
    con.execute(
        """
        insert into tournament_runs
        select $run_id, $version, current_timestamp, $sha, $dirty, $tournament,
            count(*), count(*) filter (where p.run_id = $run_id)
        from incoming as i
        inner join tournament_predictions as p using (prediction_id)
        """,
        {
            "run_id": run_id,
            "version": model_version,
            "sha": sha,
            "dirty": dirty,
            "tournament": tournament,
        },
    )
    new = con.execute(
        "select count(*) from tournament_predictions where run_id = $run_id", {"run_id": run_id}
    ).fetchone()
    con.execute("commit")
    con.close()
    return new[0] if new else 0


def forecast(
    tournament_id: str,
    model_version: str,
    seed: int = 0,
    runs: int = 10_000,
    warehouse: Path = WAREHOUSE,
    path: Path = PREDICTIONS,
) -> tuple[Result, int]:
    """Forecast one tournament with one model: bind its match_probs to the simulator, build
    the score pool from earlier finals matches, run `runs` seeded Monte Carlo runs, and
    store the results immutably. Returns the raw `Result` and how many predictions were new."""
    fmt = load_formats()[tournament_id]
    if fmt.groups is None:
        raise ValueError(f"{tournament_id}: group draw not known")
    as_of = first_match_date(fmt.kind, fmt.year, warehouse) - timedelta(days=1)
    match_probs = bind_match_probs(model_version, fmt, as_of, warehouse)
    pool = score_pool_before(as_of, warehouse)
    result = simulate(fmt, match_probs, pool, runs=runs, seed=seed)
    rows = predictions(result, model_version, datetime.combine(as_of, time.min, tzinfo=UTC))
    new = save(rows, model_version, path)
    return result, new


def main() -> None:
    for tournament_id in VALIDATION_TOURNAMENTS:
        for model_version in MODEL_VERSIONS:
            result, new = forecast(tournament_id, model_version)
            print(
                f"{tournament_id} / {model_version}: {len(result.reach)} teams, "
                f"{result.runs} runs, seed {result.seed}, {new} new predictions stored"
            )


if __name__ == "__main__":
    main()
