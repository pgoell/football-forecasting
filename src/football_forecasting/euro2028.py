"""EURO 2028 (docs/tournament-spec.md, question 3): ratings for UEFA's 55 members while the
qualifying draw has not happened, and the finals/qualifying simulator once it has.

The tournament simulator (`tournament.py`) forecasts a *finals* bracket, drawn into groups.
EURO 2028 has neither its qualifying groups nor its finals draw yet (checked
docs/data-sources.md, EURO 2028 qualifying): `tournament_formats.yaml`'s `euro2028` entry has
`groups: null`. Per docs/tournament-spec.md's Decisions ("our Elo is worse than a free
published one; the dashboard uses eloratings.net ratings through our simulator") and the
round-calibration diagnosis (docs/experiment-log.md, 2026-09-28: no fix beat `sim-v1`),
forecasting EURO 2028 once there is a draw means eloratings-v1 ratings through `sim-v1`,
unchanged.

Until then, the honest and simple thing (docs/tournament-spec.md's own fallback) is to
publish today's eloratings.net rating for every team that could play in EURO 2028, not an
invented bracket: `current_ratings()` reads each team's latest post-match rating, and
`table()` flags the 4 hosts. Unlike past EUROs, hosting is not a free finals place here
(docs/data-sources.md, EURO 2028 qualifying): all four hosts play in qualifying, drawn into
separate groups, with only a safety net of at most 2 reserved places for the best-ranked
host that still misses out. Logged immutably with `prediction_as_of` (`save_snapshot`),
never edited, so the dashboard's history can always be reread.
"""

import csv
import hashlib
import tempfile
from dataclasses import astuple, dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from football_forecasting.backtest import git_state
from football_forecasting.data import PREDICTIONS, WAREHOUSE
from football_forecasting.tournament import load_formats

MODEL_VERSION = "eloratings-v1"
SIM_VERSION = "sim-v1"  # docs/experiment-log.md, round-calibration diagnosis: no fix beat v1

# UEFA's 55 member associations (this project's team_id, dbt/seeds/team_names.csv), common
# knowledge, cross-checked against every eloratings.net-rated team in that file. Russia is a
# UEFA member but suspended from UEFA/FIFA competitions since February 2022 (ongoing): kept
# out of the "current top teams" table with a note rather than silently dropped.
UEFA_TEAMS = (
    "albania", "andorra", "armenia", "austria", "azerbaijan", "belarus", "belgium",
    "bosnia_and_herzegovina", "bulgaria", "croatia", "cyprus", "czech_republic", "denmark",
    "england", "estonia", "faroe_islands", "finland", "france", "georgia", "germany",
    "gibraltar", "greece", "hungary", "iceland", "israel", "italy", "kazakhstan", "kosovo",
    "latvia", "liechtenstein", "lithuania", "luxembourg", "malta", "moldova", "montenegro",
    "netherlands", "north_macedonia", "northern_ireland", "norway", "poland", "portugal",
    "republic_of_ireland", "romania", "russia", "san_marino", "scotland", "serbia",
    "slovakia", "slovenia", "spain", "sweden", "switzerland", "turkey", "ukraine", "wales",
)  # fmt: skip
SUSPENDED = ("russia",)


def hosts() -> tuple[str, ...]:
    """England, Scotland, Wales, Republic of Ireland (tournament_formats.yaml, sourced in
    docs/data-sources.md, Tournament formats)."""
    return load_formats()["euro2028"].hosts


@dataclass(frozen=True)
class TeamRating:
    team: str
    name: str
    rating: float
    is_host: bool


def current_ratings(warehouse: Path = WAREHOUSE) -> dict[str, float]:
    """Each team's latest known eloratings.net rating (the post-match rating of its own most
    recent rated match), not just UEFA's: callers filter to `UEFA_TEAMS`."""
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        with per_team as (
            select team1_id as team_id, match_date, rating1_post as rating
            from stg_eloratings__matches where team1_id is not null
            union all
            select team2_id, match_date, rating2_post
            from stg_eloratings__matches where team2_id is not null
        )
        select team_id, rating
        from per_team
        qualify row_number() over (partition by team_id order by match_date desc) = 1
        """
    ).fetchall()
    con.close()
    return dict(rows)


def _rows(ratings: dict[str, float], names: dict[str, str]) -> list[TeamRating]:
    """UEFA's members with a rating, hosts first then the rest, both groups sorted highest
    first. Excludes `SUSPENDED` teams (Russia)."""
    host_ids = set(hosts())
    rows = [
        TeamRating(team, names.get(team, team), ratings[team], team in host_ids)
        for team in UEFA_TEAMS
        if team in ratings and team not in SUSPENDED
    ]
    return sorted(rows, key=lambda r: (not r.is_host, -r.rating))


def table(warehouse: Path = WAREHOUSE) -> list[TeamRating]:
    """Today's table, computed live from the warehouse (`main`/the refresh task: the only
    place that reads the warehouse live, since forecasts are logged immutably before the
    dashboard, read-only, ever sees them)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    names = dict(con.execute("select team_id, martj42_name from team_names").fetchall())
    con.close()
    return _rows(current_ratings(warehouse), names)


def latest_snapshot(
    warehouse: Path = WAREHOUSE, path: Path = PREDICTIONS
) -> tuple[list[TeamRating], datetime | None]:
    """The dashboard's view: the most recently logged snapshot (`save_snapshot`), never
    recomputed live, so the page always shows exactly what was published and when."""
    con = duckdb.connect(str(path), read_only=True)
    tables = {
        r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()
    }
    if "euro2028_ratings" not in tables:
        con.close()
        return [], None
    row = con.execute("select max(prediction_as_of) from euro2028_ratings").fetchone()
    if row is None or row[0] is None:
        con.close()
        return [], None
    as_of = row[0]
    ratings = dict(
        con.execute(
            "select team, rating from euro2028_ratings where prediction_as_of = ?", [as_of]
        ).fetchall()
    )
    con.close()
    con = duckdb.connect(str(warehouse), read_only=True)
    names = dict(con.execute("select team_id, martj42_name from team_names").fetchall())
    con.close()
    return _rows(ratings, names), as_of


@dataclass(frozen=True)
class RatingSnapshot:
    prediction_id: str
    team: str
    rating: float
    model_version: str
    prediction_as_of: datetime


def snapshot(rows: list[TeamRating], prediction_as_of: datetime) -> list[RatingSnapshot]:
    return [
        RatingSnapshot(
            hashlib.sha256(f"{MODEL_VERSION}|{r.team}|{prediction_as_of}".encode()).hexdigest()[
                :16
            ],
            r.team,
            r.rating,
            MODEL_VERSION,
            prediction_as_of,
        )
        for r in rows
    ]


def save_snapshot(rows: list[RatingSnapshot], path: Path = PREDICTIONS) -> int:
    """Append this snapshot immutably (same discipline as `tournament_run.save`): never
    updates or deletes a row, only ever adds ones not already stored."""
    con = duckdb.connect(str(path))
    con.execute(
        """
        create table if not exists euro2028_ratings (
            prediction_id varchar primary key,
            team varchar not null,
            rating double not null,
            model_version varchar not null,
            prediction_as_of timestamptz not null,
            stored_at timestamptz not null default current_timestamp,
            git_sha varchar not null,
            git_dirty boolean not null
        )
        """
    )
    columns = list(RatingSnapshot.__dataclass_fields__)
    sha, dirty = git_state()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="") as f:
        csv.writer(f).writerows(astuple(r) for r in rows)
        f.flush()
        con.execute("create temp table incoming as from euro2028_ratings limit 0")
        con.execute(f"copy incoming ({', '.join(columns)}) from '{f.name}' (header false)")
    changed = con.execute(
        f"""
        select count(*) from incoming as i
        inner join euro2028_ratings as e using (prediction_id)
        where ({", ".join(f"i.{c}" for c in columns)})
            is distinct from ({", ".join(f"e.{c}" for c in columns)})
        """
    ).fetchone()
    if changed and changed[0]:
        raise ValueError(f"{changed[0]} stored ratings would change; this should never happen")
    new = con.execute(
        "select count(*) from incoming where prediction_id not in"
        " (select prediction_id from euro2028_ratings)"
    ).fetchone()
    con.execute("begin")
    con.execute(
        f"""
        insert into euro2028_ratings ({", ".join(columns)}, git_sha, git_dirty)
        select {", ".join(columns)}, $sha, $dirty from incoming
        where prediction_id not in (select prediction_id from euro2028_ratings)
        """,
        {"sha": sha, "dirty": dirty},
    )
    con.execute("commit")
    con.close()
    return new[0] if new else 0


def main() -> None:
    rows = table()
    as_of = datetime.now(UTC)
    new = save_snapshot(snapshot(rows, as_of), PREDICTIONS)
    print(f"{len(rows)} UEFA teams rated, {new} new rows logged at {as_of.isoformat()}")
    print(f"hosts: {', '.join(hosts())}")
    for r in rows[:10]:
        tag = " (host)" if r.is_host else ""
        print(f"{r.name}{tag}: {r.rating:.0f}")


if __name__ == "__main__":
    main()
