"""Matches and odds from the dbt warehouse, holdout seasons left out."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
PREDICTIONS = ROOT / "data" / "predictions.duckdb"

# docs/experiment-spec.md, Data periods. Seasons are four digits, 0506 = 2005/06.
FIRST_DEVELOPMENT_SEASON = "0506"
FIRST_VALIDATION_SEASON = "1920"
FIRST_HOLDOUT_SEASON = "2324"


@dataclass(frozen=True)
class Fixture:
    """What a model may know about a match before it is played."""

    match_id: str
    league: str
    season: str
    home_team: str
    away_team: str


@dataclass(frozen=True)
class Match:
    fixture: Fixture
    result: str  # H, D or A
    goals: tuple[int, int]  # home, away
    pre_at: datetime
    close_at: datetime
    result_at: datetime
    # home, away; None in seasons without them (D1 2002/03 to 2005/06)
    shots_on_target: tuple[int, int] | None = None
    xg: tuple[float, float] | None = None  # Understat, 2014/15 onward


def pair[T](home: T | None, away: T | None) -> tuple[T, T] | None:
    return None if home is None or away is None else (home, away)


@dataclass(frozen=True)
class Odds:
    bookmaker: str
    moment: str  # pre or close
    available_at: datetime
    is_reliable: bool
    is_aggregate: bool
    odds: tuple[float, float, float]
    probs: tuple[float, float, float]  # devigged by normalization


def leagues(warehouse: Path = WAREHOUSE) -> dict[str, tuple[str, int]]:
    """League code to (country, tier), tier 1 the top league (dbt/seeds/leagues.csv)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute("select league, country, tier from leagues").fetchall()
    con.close()
    return {league: (country, tier) for league, country, tier in rows}


def load(warehouse: Path = WAREHOUSE) -> tuple[list[Match], dict[str, list[Odds]]]:
    """Every match before the holdout, and its odds by match_id."""
    con = duckdb.connect(str(warehouse), read_only=True)
    matches = [
        Match(
            Fixture(*row[:5]),
            row[5],
            (row[6], row[7]),
            row[8],
            row[9],
            row[10],
            pair(row[11], row[12]),
            pair(row[13], row[14]),
        )
        for row in con.execute(
            """
            select match_id, league, season, home_team, away_team,
                result, home_goals, away_goals, pre_at, close_at, result_at,
                home_shots_on_target, away_shots_on_target, home_xg, away_xg
            from int_matches
            where season < ?
            order by match_id
            """,
            [FIRST_HOLDOUT_SEASON],
        ).fetchall()
    ]
    odds: dict[str, list[Odds]] = {}
    for (
        match_id,
        bookmaker,
        moment,
        available_at,
        is_reliable,
        is_aggregate,
        *prices,
    ) in con.execute(
        """
        select o.match_id, o.bookmaker, o.moment, o.available_at, o.is_reliable, b.is_aggregate,
            o.odds_home, o.odds_draw, o.odds_away, o.p_home, o.p_draw, o.p_away
        from int_odds as o
        inner join int_matches as m using (match_id)
        inner join bookmakers as b on o.bookmaker = b.code
        where m.season < ?
        order by o.match_id, o.bookmaker, o.moment
        """,
        [FIRST_HOLDOUT_SEASON],
    ).fetchall():
        oh, od, oa, ph, pd, pa = prices
        odds.setdefault(match_id, []).append(
            Odds(
                bookmaker,
                moment,
                available_at,
                is_reliable,
                is_aggregate,
                (oh, od, oa),
                (ph, pd, pa),
            )
        )
    con.close()
    return matches, odds
