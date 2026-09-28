"""Bracket tests (docs/tournament-spec.md, Simulator): fed the real group scores of each
past World Cup and EURO, the format data and standings/bracket code must reproduce the
real group tables and the real knockout pairings and champion.

Real results only, no simulation: `standings()` runs on the actual scores, and each
knockout pairing is checked against the actual match between those two teams (shootout
winner from `shootouts.csv` where the 90 minutes, or extra time, were level). If the
format data (groups, bracket template, tie-break order) is wrong, the pairing this
produces will not match any real match and the lookup below fails loudly.

WC 2026 and EURO 2028 have no `groups` in the format data (the draw is unknown or, for
2026, out of holdout bounds) and so are never parametrized here (docs/tournament-spec.md,
Rules against fooling ourselves; HOLDOUT RULE).
"""

import random

import duckdb
import pytest

from football_forecasting.data import WAREHOUSE
from football_forecasting.tournament import GroupMatch, bracket_slots, load_formats, standings, walk

# Real group standings decided by FIFA/UEFA's fair-play (disciplinary) tie-break, which we
# have no data for (no yellow/red cards in martj42/international_results), the two cases
# docs/data-sources.md records:
# - 2018 World Cup Group H: Japan above Senegal, level on points, goal difference, goals
#   scored and head-to-head; Japan had fewer yellow cards
# - 2024 EURO Group C: Denmark above Slovenia, level on points, head-to-head and overall
#   goal difference and goals scored; Denmark had fewer disciplinary points
GROUP_OVERRIDES: dict[str, dict[str, list[str]]] = {
    "wc2018": {"H": ["colombia", "japan", "senegal", "poland"]},
    "euro2024": {"C": ["england", "denmark", "slovenia", "serbia"]},
}

# Common knowledge (Wikipedia), not part of the holdout: every one of these tournaments
# finished before the spec's validation cutoff (2024-07-14).
CHAMPIONS = {
    "wc2006": "italy",
    "wc2010": "spain",
    "wc2014": "germany",
    "wc2018": "france",
    "wc2022": "argentina",
    "euro2008": "spain",
    "euro2012": "spain",
    "euro2016": "portugal",
    "euro2020": "italy",
    "euro2024": "spain",
}


def real_group_matches(
    con: duckdb.DuckDBPyConnection, finals: str, edition: int, teams: tuple[str, ...]
) -> list[GroupMatch]:
    """The group match between each pair of `teams` (90-minute score): the earliest of any
    matches between them in this tournament, in case a rematch happened in the knockout."""
    placeholders = ",".join("?" * len(teams))
    rows = con.execute(
        f"""
        select home_team_id, away_team_id, home_score_90, away_score_90
        from stg_international_results__matches
        where finals = ? and edition = ?
            and home_team_id in ({placeholders}) and away_team_id in ({placeholders})
        order by match_date
        """,
        [finals, edition, *teams, *teams],
    ).fetchall()
    matches, seen = [], set()
    for home, away, home_goals, away_goals in rows:
        pair = frozenset((home, away))
        if pair in seen:
            continue
        seen.add(pair)
        matches.append(GroupMatch(home, away, home_goals, away_goals))
    return matches


def real_decider(con: duckdb.DuckDBPyConnection, finals: str, edition: int):
    """decide(a, b) for `walk`: the real winner of the match between a and b, penalty
    shootouts (shootouts.csv, via stg_international_results__matches.shootout_winner)
    breaking a full-time draw. A pair can have played twice (once in the group stage,
    once more in the knockout stage, e.g. Spain v Italy at EURO 2012): the knockout
    meeting is always the later of the two, so take the latest."""

    def decide(team_a: str, team_b: str) -> str:
        rows = con.execute(
            """
            select home_team_id, away_team_id, home_score, away_score,
                shootout_winner, home_team, away_team
            from stg_international_results__matches
            where finals = ? and edition = ?
                and ((home_team_id = ? and away_team_id = ?)
                    or (home_team_id = ? and away_team_id = ?))
            order by match_date desc
            """,
            [finals, edition, team_a, team_b, team_b, team_a],
        ).fetchall()
        assert 1 <= len(rows) <= 2, f"expected 1-2 {team_a} v {team_b} matches, found {len(rows)}"
        home_id, away_id, home_goals, away_goals, shootout_winner, home_name, _ = rows[0]
        if home_goals != away_goals:
            return home_id if home_goals > away_goals else away_id
        assert shootout_winner is not None, f"{team_a} v {team_b} level with no shootout winner"
        return home_id if shootout_winner == home_name else away_id

    return decide


@pytest.mark.parametrize(
    ("format_id", "finals", "edition"),
    [
        ("wc2006", "WC", 2006),
        ("wc2010", "WC", 2010),
        ("wc2014", "WC", 2014),
        ("wc2018", "WC", 2018),
        ("wc2022", "WC", 2022),
        ("euro2008", "EURO", 2008),
        ("euro2012", "EURO", 2012),
        ("euro2016", "EURO", 2016),
        ("euro2020", "EURO", 2020),
        ("euro2024", "EURO", 2024),
    ],
)
def test_replay_reproduces_the_real_bracket_and_champion(format_id, finals, edition):
    fmt = load_formats()[format_id]
    assert fmt.groups is not None
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        group_matches = {
            letter: real_group_matches(con, finals, edition, teams)
            for letter, teams in fmt.groups.items()
        }
        overrides = GROUP_OVERRIDES.get(format_id, {})
        rng = random.Random(0)
        order = {
            letter: standings(
                teams, group_matches[letter], fmt.tiebreak, rng, override=overrides.get(letter)
            )
            for letter, teams in fmt.groups.items()
        }
        slots = bracket_slots(fmt, order, group_matches, rng)
        _, champion = walk(fmt.knockout_seeds, slots, real_decider(con, finals, edition))
    finally:
        con.close()
    assert champion == CHAMPIONS[format_id]


def test_wc2026_and_euro2028_have_no_group_draw():
    formats = load_formats()
    assert formats["wc2026"].groups is None
    assert formats["euro2028"].groups is None
