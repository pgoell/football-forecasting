import dataclasses
import random

import pytest

from football_forecasting.tournament import (
    Format,
    GroupMatch,
    MatchProbs,
    bracket_slots,
    decide_knockout,
    home_of,
    load_formats,
    rank_thirds,
    round_sequence,
    simulate,
    simulate_group,
    standings,
    walk,
)

TEAMS = ["a", "b", "c", "d"]


def test_load_formats_are_internally_consistent():
    """Every format's team count and knockout bracket size agree with its own group
    count and best-third rule, and 2026's third-place table has one row per possible
    set of 8 qualifying groups out of 12 (C(12, 8) = 495)."""
    formats = load_formats()
    assert {"wc2006", "wc2026", "euro2008", "euro2028"} <= formats.keys()
    for fmt in formats.values():
        if fmt.groups is None:
            continue
        assert all(len(teams) == 4 for teams in fmt.groups.values())
        assert len(set().union(*fmt.groups.values())) == 4 * len(fmt.groups)
        slots = 2 * len(fmt.groups) + fmt.third_place_advance
        assert 2 * len(fmt.knockout_seeds) == slots
    assert formats["wc2026"].groups is None
    assert formats["euro2028"].groups is None
    wc2026_table = formats["wc2026"].third_place_table
    euro2016_table = formats["euro2016"].third_place_table
    assert wc2026_table is not None and len(wc2026_table) == 495
    assert euro2016_table is not None and len(euro2016_table) == 15


def round_robin(scores: dict[tuple[str, str], tuple[int, int]]) -> list[GroupMatch]:
    return [GroupMatch(h, a, hg, ag) for (h, a), (hg, ag) in scores.items()]


def test_standings_orders_by_points_then_goal_difference():
    matches = round_robin(
        {
            ("a", "b"): (2, 0),
            ("c", "d"): (1, 1),
            ("a", "c"): (3, 0),
            ("b", "d"): (0, 0),
            ("a", "d"): (1, 1),
            ("b", "c"): (0, 0),
        }
    )
    # a: W W D = 7 pts, gd +5; d: D D D = 3 pts, gd 0; b and c both 2 pts, tied head-to-head
    # (0-0), separated by overall goal difference: b -2, c -3
    order = standings(TEAMS, matches, "wc", random.Random(0))
    assert order == ["a", "d", "b", "c"]


def test_wc_and_euro_rulesets_differ_on_tied_points():
    # a and b both finish on 4 points (d tops the group on 5, c is bottom on 3, neither tied
    # with anyone): a beat b head-to-head 1-0, but b thrashed c and drew d, so b's overall
    # goal difference (+4) beats a's (0). WC breaks the tie by overall goal difference first
    # (b above a); EURO breaks it by head-to-head first (a beat b, so a above b).
    matches = round_robin(
        {
            ("a", "b"): (1, 0),
            ("a", "c"): (0, 1),
            ("a", "d"): (0, 0),
            ("b", "c"): (5, 0),
            ("b", "d"): (0, 0),
            ("c", "d"): (0, 2),
        }
    )
    assert standings(TEAMS, matches, "wc", random.Random(0)) == ["d", "b", "a", "c"]
    assert standings(TEAMS, matches, "euro", random.Random(0)) == ["d", "a", "b", "c"]


def test_standings_falls_back_to_random_when_fully_tied():
    # every team draws every game 0-0: fully tied on every computable criterion
    pairs = [("a", "b"), ("c", "d"), ("a", "c"), ("b", "d"), ("a", "d"), ("b", "c")]
    matches = round_robin(dict.fromkeys(pairs, (0, 0)))
    order = standings(TEAMS, matches, "wc", random.Random(0))
    assert sorted(order) == TEAMS  # a permutation, chosen by the random stand-in


def test_standings_override_bypasses_computation():
    matches = round_robin({("a", "b"): (0, 0)})
    order = standings(["a", "b"], matches, "wc", random.Random(0), override=["b", "a"])
    assert order == ["b", "a"]


def test_rank_thirds_orders_by_points_goal_difference_goals():
    group_matches = {
        "A": round_robin({("x", "a"): (0, 3)}),  # a: 3 pts, gd 3, gf 3
        "B": round_robin({("x", "b"): (1, 1)}),  # b: 1 pt
        "C": round_robin({("x", "c"): (0, 0)}),  # c: 1 pt, but gd 0 < b's own (also 0)... see below
    }
    order = rank_thirds([("A", "a"), ("B", "b"), ("C", "c")], group_matches, random.Random(0))
    assert order[0] == "A"


def test_rank_thirds_override():
    entries = [("A", "a"), ("B", "b")]
    assert rank_thirds(entries, {}, random.Random(0), override=["B", "A"]) == ["B", "A"]


def test_round_sequence():
    assert round_sequence(8) == ["round_of_16", "quarterfinal", "semifinal", "final"]
    assert round_sequence(16) == [
        "round_of_32",
        "round_of_16",
        "quarterfinal",
        "semifinal",
        "final",
    ]
    assert round_sequence(4) == ["quarterfinal", "semifinal", "final"]


def test_walk_folds_the_bracket_in_seed_order():
    seeds = [("1A", "2B"), ("1C", "2D"), ("1B", "2A"), ("1D", "2C")]
    slots = {"1A": "a", "2B": "b", "1C": "c", "2D": "d", "1B": "e", "2A": "f", "1D": "g", "2C": "h"}
    # always the first-listed team wins
    reached, champion = walk(seeds, slots, lambda x, y: x)
    assert reached["quarterfinal"] == {"a", "b", "c", "d", "e", "f", "g", "h"}
    # winners a, c, e, g fold into semifinal pairs (a, c) and (e, g)
    assert reached["semifinal"] == {"a", "c", "e", "g"}
    assert reached["final"] == {"a", "e"}
    assert champion == "a"


def test_bracket_slots_places_top_two_and_best_thirds():
    fmt = Format(
        id="test",
        kind="EURO",
        year=2000,
        format_version="test-v1",
        hosts=(),
        groups={"A": ("a1", "a2", "a3", "a4"), "B": ("b1", "b2", "b3", "b4")},
        third_place_advance=1,
        third_place_table={("A",): {"A": 1}, ("B",): {"B": 1}},
        knockout_seeds=(("1A", "2B"), ("1B", "3-1")),
        tiebreak="euro",
    )
    order = {"A": ["a1", "a2", "a3", "a4"], "B": ["b1", "b4", "b2", "b3"]}
    group_matches = {
        "A": round_robin({("a3", "x"): (5, 0)}),
        "B": round_robin({("b2", "x"): (0, 0)}),
    }
    slots = bracket_slots(fmt, order, group_matches, random.Random(0))
    assert slots == {"1A": "a1", "2A": "a2", "1B": "b1", "2B": "b4", "3-1": "a3"}


def test_home_of():
    assert home_of("a", "b", {"a"}) == "a"
    assert home_of("a", "b", {"b"}) == "b"
    assert home_of("a", "b", set()) is None
    assert home_of("a", "b", {"a", "b"}) is None


def test_decide_knockout_uses_share_of_win_chances_on_a_draw():
    # p_draw = 1: the 90-minute result is always a draw; team_a's share is p_home / (p_home
    # + p_away), here 1.0, so it always goes through.
    def always_draw(a: str, b: str, home: str | None) -> tuple[float, float, float]:
        return (0.4, 1.0, 0.0)

    for seed in range(20):
        assert decide_knockout("x", "y", None, always_draw, random.Random(seed)) == "x"


def equal_probs(a: str, b: str, home: str | None) -> tuple[float, float, float]:
    """Stand-in match_probs #1: every team equally likely (docs/tournament-spec.md,
    Simulator: a stand-in for testing, not a forecast model)."""
    return (1 / 3, 1 / 3, 1 / 3)


def rating_match_probs(
    ratings: dict[str, float], home_advantage: float = 100.0, draw: float = 0.25
) -> MatchProbs:
    """Stand-in match_probs #2: a fixed draw probability, the rest split by a logistic on
    the rating difference (plus home_advantage for the listed host, if any)."""

    def probs(team_a: str, team_b: str, home: str | None) -> tuple[float, float, float]:
        diff = ratings.get(team_a, 1500.0) - ratings.get(team_b, 1500.0)
        diff += home_advantage if home == team_a else -home_advantage if home == team_b else 0.0
        p_a = 1 / (1 + 10 ** (-diff / 400))
        return (p_a * (1 - draw), draw, (1 - p_a) * (1 - draw))

    return probs


EQUAL_POOL = {"H": [(1, 0), (2, 0)], "D": [(0, 0), (1, 1)], "A": [(0, 1), (0, 2)]}


def test_simulate_group_draws_scores_from_the_pool():
    pool = {"H": [(2, 0)], "D": [(1, 1)], "A": [(0, 2)]}
    matches = simulate_group(TEAMS, (), equal_probs, pool, random.Random(0))
    assert len(matches) == 6
    for m in matches:
        assert (m.home_goals, m.away_goals) in {(2, 0), (1, 1), (0, 2)}


def test_rating_match_probs_favours_the_stronger_team_and_the_host():
    ratings = {"strong": 1700.0, "weak": 1300.0}
    probs = rating_match_probs(ratings)
    p_home, p_draw, p_away = probs("strong", "weak", None)
    assert p_home > p_away
    assert p_home + p_draw + p_away == pytest.approx(1.0)
    # the same match, but weak is the host: its chances improve, strong's fall
    p_home_h, _, p_away_h = probs("strong", "weak", "weak")
    assert p_away_h > p_away
    assert p_home_h < p_home


def euro16_format() -> Format:
    return Format(
        id="test-euro16",
        kind="EURO",
        year=2000,
        format_version="test-v1",
        hosts=(),
        groups={
            "A": ("a1", "a2", "a3", "a4"),
            "B": ("b1", "b2", "b3", "b4"),
            "C": ("c1", "c2", "c3", "c4"),
            "D": ("d1", "d2", "d3", "d4"),
        },
        third_place_advance=0,
        third_place_table=None,
        knockout_seeds=(("1A", "2B"), ("1C", "2D"), ("1B", "2A"), ("1D", "2C")),
        tiebreak="euro",
    )


def test_simulate_reach_probabilities_are_monotone_and_sum_correctly():
    result = simulate(euro16_format(), equal_probs, EQUAL_POOL, runs=500, seed=0)
    assert result.runs == 500
    assert result.format_id == "test-euro16"
    for reach in result.reach.values():
        assert reach["quarterfinal"] >= reach["semifinal"] >= reach["final"] >= reach["win"]
        for p in reach.values():
            assert 0 <= p <= 1
    assert sum(reach["win"] for reach in result.reach.values()) == pytest.approx(1.0)


def test_simulate_reach_quarterfinal_is_roughly_half_for_equal_teams():
    result = simulate(euro16_format(), equal_probs, EQUAL_POOL, runs=4000, seed=0)
    for reach in result.reach.values():
        assert 0.35 < reach["quarterfinal"] < 0.65


def test_simulate_runs_on_a_real_loaded_format():
    """End-to-end sanity check on real format data (real bracket template and
    third-place table), not just the small synthetic format above."""
    fmt = load_formats()["euro2024"]
    assert fmt.groups is not None
    result = simulate(fmt, equal_probs, EQUAL_POOL, runs=200, seed=0)
    assert result.runs == 200
    teams = [t for group in fmt.groups.values() for t in group]
    assert set(result.reach) == set(teams)
    for reach in result.reach.values():
        assert reach["round_of_16"] >= reach["quarterfinal"] >= reach["semifinal"]
        assert reach["semifinal"] >= reach["final"] >= reach["win"]
    assert sum(reach["win"] for reach in result.reach.values()) == pytest.approx(1.0)


def test_simulate_requires_known_groups():
    fmt = euro16_format()
    unknown = dataclasses.replace(fmt, groups=None)
    with pytest.raises(ValueError, match="group draw not known"):
        simulate(unknown, equal_probs, EQUAL_POOL)
