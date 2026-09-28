"""World Cup and EURO group draws and knockout brackets, and the Monte Carlo
simulator that runs a format forward from a match-probability function.

Formats are data (`tournament_formats.yaml`), not code: group membership,
tie-break order, and the knockout bracket template for each edition. Sources
for every rule and every group are recorded in docs/data-sources.md.

Fair play (disciplinary points) and drawing of lots are the last FIFA/UEFA
tie-breakers, used only when every computable criterion (points, goal
difference, goals scored, head-to-head) is still equal. We have no
disciplinary data, so both are implemented as one random draw, noted wherever
it decides something (`standings`, `rank_thirds`).

`MatchProbs` takes no `as_of`: a tournament run is one moment (docs/tournament-spec.md,
Targets, Tournament horizon), so a model with an `as_of` argument, such as the planned
national-elo-v1, is bound to the tournament's date before it is passed in here, e.g.
`lambda a, b, home: elo.match_probs(a, b, home, as_of=draw_date)`.
"""

import itertools
import random
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

Probs = tuple[float, float, float]
# (team_a, team_b, home_team_or_None) -> (P(a wins), P(draw), P(b wins))
MatchProbs = Callable[[str, str, str | None], Probs]
# outcome ("H" a won, "D" draw, "A" b won) -> pool of historical (goals_a, goals_b) scores
ScorePool = Mapping[str, Sequence[tuple[int, int]]]

FORMATS_FILE = Path(__file__).with_name("tournament_formats.yaml")

# round name by the number of teams entering it (round_sequence)
ROUND_NAMES = {32: "round_of_32", 16: "round_of_16", 8: "quarterfinal", 4: "semifinal", 2: "final"}


@dataclass(frozen=True)
class GroupMatch:
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class Format:
    id: str
    kind: str  # WC or EURO
    year: int
    format_version: str
    hosts: tuple[str, ...]
    groups: dict[str, tuple[str, ...]] | None  # None: draw not known (WC 2026, EURO 2028)
    third_place_advance: int  # 0, 4 or 8 best third-placed teams that advance
    # qualifying groups (sorted letters) -> {group letter: bracket position 1..third_place_advance}
    third_place_table: dict[tuple[str, ...], dict[str, int]] | None
    knockout_seeds: tuple[tuple[str, str], ...]  # first knockout round, in bracket order
    tiebreak: str  # "wc" or "euro"
    # Venue country per match slot (docs/tournament-spec.md, Simulator; docs/data-sources.md,
    # Tournament formats): `venue` when every match of the tournament is in one country (a
    # single host); else `group_venues`/`knockout_venues` when known match by match (EURO
    # 2020's 11 host countries). All None when the venues are not known (EURO 2028): `home_of`
    # then falls back to `hosts`.
    venue: str | None = None
    group_venues: dict[str, tuple[str, ...]] | None = (
        None  # letter -> one per combinations(group, 2)
    )
    knockout_venues: dict[str, tuple[str, ...]] | None = (
        None  # round name -> one per match, bracket order
    )


def load_formats(path: Path = FORMATS_FILE) -> dict[str, Format]:
    raw = yaml.safe_load(path.read_text())
    shapes = raw["shapes"]
    formats = {}
    for edition in raw["editions"]:
        shape = shapes[edition["shape"]]
        groups = (
            {letter: tuple(teams) for letter, teams in edition["groups"].items()}
            if edition.get("groups")
            else None
        )
        table_raw = edition.get("third_place_table", shape.get("third_place_table"))
        table = (
            {tuple(sorted(combo.split(","))): positions for combo, positions in table_raw.items()}
            if table_raw
            else None
        )
        seeds = edition.get("knockout_seeds", shape["knockout_seeds"])
        venues = edition.get("venues")
        formats[edition["id"]] = Format(
            id=edition["id"],
            kind=edition["kind"],
            year=edition["year"],
            format_version=edition.get("format_version", shape["format_version"]),
            hosts=tuple(edition.get("hosts", [])),
            groups=groups,
            third_place_advance=shape.get("third_place_advance", 0),
            third_place_table=table,
            knockout_seeds=tuple(tuple(pair) for pair in seeds),
            tiebreak=shape["tiebreak"],
            venue=edition.get("venue"),
            group_venues={letter: tuple(v) for letter, v in venues["groups"].items()}
            if venues
            else None,
            knockout_venues={name: tuple(v) for name, v in venues["knockout"].items()}
            if venues
            else None,
        )
    return formats


def home_of(
    team_a: str, team_b: str, hosts: Collection[str], venue: str | None = None
) -> str | None:
    """The home team: whichever of the two plays in its own country, by the match's real
    venue (`venue`, docs/tournament-spec.md: a team, host or not, is only ever home in its
    own country). Falls back to the old rule, exactly one of the two a tournament host, only
    when the venue is not known (`venue` is None: EURO 2028, docs/data-sources.md)."""
    if venue is not None:
        return team_a if venue == team_a else team_b if venue == team_b else None
    a_host, b_host = team_a in hosts, team_b in hosts
    return team_a if a_host and not b_host else team_b if b_host and not a_host else None


def _draw_outcome(probs: Probs, rng: random.Random) -> str:
    p_home, p_draw, _ = probs
    x = rng.random()
    return "H" if x < p_home else "D" if x < p_home + p_draw else "A"


def _stats(team: str, matches: Sequence[GroupMatch]) -> tuple[int, int, int]:
    """Points, goal difference and goals for, over the matches `team` played."""
    points = goals_for = goals_against = 0
    for m in matches:
        if team not in (m.home, m.away):
            continue
        gf, ga = (m.home_goals, m.away_goals) if team == m.home else (m.away_goals, m.home_goals)
        goals_for += gf
        goals_against += ga
        points += 3 if gf > ga else 1 if gf == ga else 0
    return points, goals_for - goals_against, goals_for


_CRITERION_INDEX = {"points": 0, "goal_difference": 1, "goals_for": 2}

Criterion = Callable[[str, Sequence[str], Sequence[GroupMatch]], tuple[int, ...]]


def _overall(name: str) -> Criterion:
    """A criterion over every match of the group, ignoring which teams are still tied."""
    index = _CRITERION_INDEX[name]

    def crit(team: str, teams: Sequence[str], matches: Sequence[GroupMatch]) -> tuple[int, ...]:
        return (_stats(team, matches)[index],)

    return crit


def _head_to_head(
    team: str, teams: Sequence[str], matches: Sequence[GroupMatch]
) -> tuple[int, ...]:
    """Points, goal difference and goals scored, in matches between just the tied teams,
    compared together (FIFA/UEFA: points, then goal difference, then goals scored, all
    from the same head-to-head matches, not recomputed match by match)."""
    relevant = [m for m in matches if {m.home, m.away} <= set(teams)]
    return _stats(team, relevant)


# docs/data-sources.md, Tournament formats: 2006-2022 FIFA rules order overall criteria
# first, then head-to-head among the tied teams; UEFA rules order head-to-head first, then
# overall. From 2026, FIFA switches to the UEFA order (head-to-head first).
RULESETS = {
    "wc": [_overall("points"), _overall("goal_difference"), _overall("goals_for"), _head_to_head],
    "euro": [_overall("points"), _head_to_head, _overall("goal_difference"), _overall("goals_for")],
}
RULESETS["wc2026"] = RULESETS["euro"]


def _resolve(
    teams: list[str],
    matches: Sequence[GroupMatch],
    criteria: Sequence[Criterion],
    rng: random.Random,
) -> list[str]:
    if len(teams) <= 1:
        return teams
    if not criteria:
        rng.shuffle(teams)  # fair play, then drawing of lots: not modeled, see module docstring
        return teams
    crit, *rest = criteria
    scored = sorted(teams, key=lambda t: crit(t, teams, matches), reverse=True)
    ordered = []
    for _, tier in itertools.groupby(scored, key=lambda t: crit(t, teams, matches)):
        tier = list(tier)
        if len(tier) <= 1:
            ordered += tier
        elif crit is _head_to_head and len(tier) < len(teams):
            # some teams were separated; UEFA/FIFA reapply head-to-head fresh to the rest,
            # from a new (smaller) head-to-head, before falling through to `rest`
            ordered += _resolve(tier, matches, criteria, rng)
        else:
            ordered += _resolve(tier, matches, rest, rng)
    return ordered


def standings(
    teams: Sequence[str],
    matches: Sequence[GroupMatch],
    ruleset: str,
    rng: random.Random,
    override: Sequence[str] | None = None,
) -> list[str]:
    """Teams of one group, 1st to last. `override`: the real final order, for a group a
    past tournament decided by fair play or lots (docs/data-sources.md)."""
    if override is not None:
        return list(override)
    return _resolve(list(teams), matches, RULESETS[ruleset], rng)


def rank_thirds(
    entries: Sequence[tuple[str, str]],
    group_matches: Mapping[str, Sequence[GroupMatch]],
    rng: random.Random,
    override: Sequence[str] | None = None,
) -> list[str]:
    """Third-placed teams' group letters, best to worst, by points/goal difference/goals
    scored (no head-to-head: they are in different groups). `entries`: (letter, team)."""
    if override is not None:
        return list(override)
    scored = sorted(entries, key=lambda e: _stats(e[1], group_matches[e[0]]), reverse=True)
    ordered = []
    for _, tier in itertools.groupby(scored, key=lambda e: _stats(e[1], group_matches[e[0]])):
        letters = [letter for letter, _ in tier]
        if len(letters) > 1:
            rng.shuffle(letters)  # fair play, then drawing of lots: not modeled
        ordered += letters
    return ordered


def bracket_slots(
    fmt: Format,
    order: Mapping[str, Sequence[str]],
    group_matches: Mapping[str, Sequence[GroupMatch]],
    rng: random.Random,
    thirds_override: Sequence[str] | None = None,
) -> dict[str, str]:
    """Slot code ("1A", "2A", "3-1", ...) to team, for the first knockout round."""
    slots = {}
    thirds = []
    for letter, teams in order.items():
        slots[f"1{letter}"] = teams[0]
        slots[f"2{letter}"] = teams[1]
        if fmt.third_place_advance:
            thirds.append((letter, teams[2]))
    if fmt.third_place_advance:
        assert fmt.third_place_table is not None
        ranked = rank_thirds(thirds, group_matches, rng, thirds_override)
        qualifying = tuple(sorted(ranked[: fmt.third_place_advance]))
        positions = fmt.third_place_table[qualifying]
        by_letter = dict(thirds)
        for letter, position in positions.items():
            slots[f"3-{position}"] = by_letter[letter]
    return slots


def round_sequence(first_round_pairs: int) -> list[str]:
    """Round names from the first knockout round to the final, by teams entering each."""
    names = []
    teams = first_round_pairs * 2
    while teams >= 2:
        names.append(ROUND_NAMES[teams])
        teams //= 2
    return names


def walk(
    seeds: Sequence[tuple[str, str]],
    slots: Mapping[str, str],
    decide: Callable[[str, str], str],
) -> tuple[dict[str, set[str]], str]:
    """Play out the bracket from `seeds` (slot codes, bracket order) with `decide(a, b)`
    returning the winner. Returns each round's participants and the champion."""
    names = round_sequence(len(seeds))
    current = [(slots[a], slots[b]) for a, b in seeds]
    reached: dict[str, set[str]] = {}
    champion = ""
    for name in names:
        reached[name] = {team for pair in current for team in pair}
        winners = [decide(a, b) for a, b in current]
        champion = winners[0]
        current = list(zip(winners[0::2], winners[1::2], strict=False))
    return reached, champion


def decide_knockout(
    team_a: str, team_b: str, home: str | None, match_probs: MatchProbs, rng: random.Random
) -> str:
    """A 90-minute draw goes through with each team's share of its win chances
    (docs/tournament-spec.md, Simulator): extra time and penalties are not modeled apart."""
    p_home, p_draw, p_away = match_probs(team_a, team_b, home)
    outcome = _draw_outcome((p_home, p_draw, p_away), rng)
    if outcome == "H":
        return team_a
    if outcome == "A":
        return team_b
    share_home = p_home / (p_home + p_away) if p_home + p_away > 0 else 0.5
    return team_a if rng.random() < share_home else team_b


def simulate_group(
    teams: Sequence[str],
    hosts: Collection[str],
    match_probs: MatchProbs,
    score_pool: ScorePool,
    rng: random.Random,
    venues: Sequence[str | None] | None = None,
) -> list[GroupMatch]:
    """`venues`: one venue country per pair of `teams`, in `itertools.combinations` order
    (`Format.group_venues[letter]`), or None if not known."""
    matches = []
    for i, (a, b) in enumerate(itertools.combinations(teams, 2)):
        venue = venues[i] if venues is not None else None
        probs = match_probs(a, b, home_of(a, b, hosts, venue))
        outcome = _draw_outcome(probs, rng)
        pool = score_pool[outcome]
        goals_a, goals_b = pool[rng.randrange(len(pool))]
        matches.append(GroupMatch(a, b, goals_a, goals_b))
    return matches


@dataclass(frozen=True)
class Result:
    format_id: str
    format_version: str
    seed: int
    runs: int
    reach: dict[str, dict[str, float]]  # team -> {round name or "win": probability}


def _group_venues(fmt: Format, letter: str, teams: Sequence[str]) -> list[str | None] | None:
    """One venue country per pair of `teams` (`simulate_group`'s `venues`), or None if the
    tournament's venues are not known at all."""
    if fmt.venue is not None:
        return [fmt.venue] * (len(teams) * (len(teams) - 1) // 2)
    if fmt.group_venues is not None:
        return list(fmt.group_venues[letter])
    return None


def _knockout_venues(fmt: Format) -> list[str | None] | None:
    """One venue country per knockout match, in the order `walk` calls `decide` (each round
    in `round_sequence` order, bracket order within a round), or None if not known."""
    if fmt.venue is not None:
        return [fmt.venue] * (2 * len(fmt.knockout_seeds) - 1)
    if fmt.knockout_venues is not None:
        names = round_sequence(len(fmt.knockout_seeds))
        return [v for name in names for v in fmt.knockout_venues[name]]
    return None


def simulate(
    fmt: Format, match_probs: MatchProbs, score_pool: ScorePool, runs: int = 10_000, seed: int = 0
) -> Result:
    """Run the format forward `runs` times: draw each group, seed the bracket, play it
    out, and count how often each team reaches each round and wins."""
    if fmt.groups is None:
        raise ValueError(f"{fmt.id}: group draw not known")
    rng = random.Random(seed)
    teams = [team for group in fmt.groups.values() for team in group]
    rounds = [*round_sequence(len(fmt.knockout_seeds)), "win"]
    counts = {team: dict.fromkeys(rounds, 0) for team in teams}
    group_venues = {
        letter: _group_venues(fmt, letter, group) for letter, group in fmt.groups.items()
    }
    knockout_venues = _knockout_venues(fmt)
    for _ in range(runs):
        group_matches = {
            letter: simulate_group(
                group, fmt.hosts, match_probs, score_pool, rng, group_venues[letter]
            )
            for letter, group in fmt.groups.items()
        }
        order = {
            letter: standings(group, group_matches[letter], fmt.tiebreak, rng)
            for letter, group in fmt.groups.items()
        }
        slots = bracket_slots(fmt, order, group_matches, rng)
        venue_iter = iter(knockout_venues) if knockout_venues is not None else None

        def decide(a: str, b: str, venue_iter=venue_iter) -> str:
            venue = next(venue_iter) if venue_iter is not None else None
            return decide_knockout(a, b, home_of(a, b, fmt.hosts, venue), match_probs, rng)

        reached, champion = walk(fmt.knockout_seeds, slots, decide)
        for name, teams_in in reached.items():
            for team in teams_in:
                counts[team][name] += 1
        counts[champion]["win"] += 1
    reach = {team: {name: n / runs for name, n in c.items()} for team, c in counts.items()}
    return Result(fmt.id, fmt.format_version, seed, runs, reach)
