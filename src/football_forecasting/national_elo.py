"""National-team Elo (docs/tournament-spec.md, MODEL step).

`national-elo-v1`: one Elo rating per men's national team, walk-forward over
every international from 1872 (`NationalElo`). K is eloratings.net's published
per-tournament weight (`match_weight`); the rating change is also scaled by a
goal-difference multiplier, again eloratings.net's own (`goal_multiplier`).
Home advantage applies only when the match is not at a neutral venue (a real
home match, hosts at their own tournament included): `int_international_matches
.neutral` already encodes this (checked against WC/EURO host matches). Awarded
matches (a forfeit, not a played result; dbt/seeds/international_awarded_matches
.csv) update no rating.

Ratings map to 90-minute H/D/A by elo-v1's ordered logit
(`models.fit_ordered_logit` / `models.ordered_logit`) on the rating gap,
refit before each WC or EURO finals tournament on every earlier finals match
with a reliable 90-minute score (`TournamentLogit`), then reused for every
match of that tournament (mid-tournament results do not change the fit).

Two benchmarks share the same machinery: `NaiveTournamentBenchmark` (base
rates, split by whether the host plays) and `EloRatingsBenchmark`
(eloratings.net's own published pre-match ratings through the same kind of
ordered logit, fit on the same matches).

`match_probs()` is the interface the tournament simulator calls.

Capped at the end of development (`FIRST_VALIDATION_DATE`) until a review
authorizes scoring validation (docs/tournament-spec.md: "Stop after
development and report"): `load()` never returns a later match unless told to.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import duckdb

from football_forecasting.data import WAREHOUSE
from football_forecasting.models import OUTCOMES, Probs, fit_ordered_logit, ordered_logit

# docs/tournament-spec.md, Data periods.
FIRST_DEVELOPMENT_DATE = date(2006, 1, 1)
FIRST_VALIDATION_DATE = date(2020, 1, 1)
FIRST_HOLDOUT_DATE = date(2024, 7, 15)

HOME_ADVANTAGE = 100.0  # eloratings.net's published value

# eloratings.net's published K by tournament category (World Football Elo
# Ratings): 60 World Cup finals, 50 continental championship and
# intercontinental finals, 40 World Cup/continental qualifiers and Nations
# Leagues, 20 friendlies, 30 everything else.
CONTINENTAL_FINALS = {
    "UEFA Euro",
    "Copa América",
    "African Cup of Nations",
    "AFC Asian Cup",
    "Gold Cup",
    "CONCACAF Championship",
    "Oceania Nations Cup",
    "Confederations Cup",
}


def match_weight(tournament: str) -> float:
    if tournament == "FIFA World Cup":
        return 60.0
    if tournament in CONTINENTAL_FINALS:
        return 50.0
    if tournament == "Friendly":
        return 20.0
    if "qualification" in tournament or "Nations League" in tournament:
        return 40.0
    return 30.0


def goal_multiplier(goal_difference: int) -> float:
    """eloratings.net's G: 1 for a draw or 1-goal win, 1.5 for 2, (11+N)/8 for 3+."""
    n = abs(goal_difference)
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11 + n) / 8


def outcome(home: int, away: int) -> str:
    return "H" if home > away else "A" if home < away else "D"


@dataclass(frozen=True)
class NationalMatch:
    match_id: str
    match_date: date
    home_team_id: str
    away_team_id: str
    home_score: int  # full time, extra time included, shootout excluded
    away_score: int
    home_score_90: int | None
    away_score_90: int | None
    score_90_reliable: bool
    neutral: bool
    awarded: bool  # a forfeit, not a played result; ratings do not update on it
    tournament: str
    finals: str | None  # 'WC', 'EURO', or None
    edition: int | None
    elo_home_rating_pre: int | None
    elo_away_rating_pre: int | None


def load(warehouse: Path = WAREHOUSE, before: date = FIRST_VALIDATION_DATE) -> list[NationalMatch]:
    """Every international match with both teams in seeds/team_names.csv,
    oldest first, strictly before `before`. Defaults to the end of development:
    pass a later date only once a review has authorized scoring validation or
    the holdout (docs/tournament-spec.md)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select match_id, match_date, home_team_id, away_team_id,
            home_score, away_score, home_score_90, away_score_90,
            score_90_reliable, neutral, awarded, tournament, finals, edition,
            elo_home_rating_pre, elo_away_rating_pre
        from int_international_matches
        where home_team_id is not null and away_team_id is not null
            and match_date < ?
        order by match_date, match_id
        """,
        [before],
    ).fetchall()
    con.close()
    return [NationalMatch(*row) for row in rows]


def tournament_windows(matches: list[NationalMatch]) -> list[tuple[date, date]]:
    """The (first, last) match_date of every WC/EURO finals tournament in
    `matches`: a prediction that falls inside one must not refit the ordered
    logit on that same tournament's own, earlier matches."""
    spans: dict[tuple[str, int], list[date]] = defaultdict(list)
    for m in matches:
        if m.finals is not None and m.edition is not None:
            spans[m.finals, m.edition].append(m.match_date)
    return [(min(ds), max(ds)) for ds in spans.values()]


class TournamentLogit:
    """An ordered logit on a rating gap, refit before each WC/EURO finals
    tournament on every earlier reliable match, reused for every match of that
    tournament (docs/tournament-spec.md). `windows`: see `tournament_windows`."""

    def __init__(self, windows: list[tuple[date, date]]) -> None:
        self.windows = windows
        self.history: list[tuple[date, float, int]] = []  # match_date, gap, 90-min outcome index
        self.cutoff: date | None = None
        self.params = None

    def add(self, match_date: date, gap: float, outcome_index: int) -> None:
        self.history.append((match_date, gap, outcome_index))

    def _cutoff(self, as_of: date) -> date:
        for start, end in self.windows:
            if start <= as_of <= end:
                return start
        return as_of

    def predict(self, as_of: date, gap: float) -> Probs | None:
        if not self.history:
            return None
        cutoff = self._cutoff(as_of)
        if cutoff != self.cutoff:
            train = [(g, o) for d, g, o in self.history if d < cutoff]
            if not train:
                return None
            self.params = fit_ordered_logit(train)
            self.cutoff = cutoff
        if self.params is None:
            return None
        return ordered_logit(self.params, gap / 400)


class NationalElo:
    """national-elo-v1: see the module docstring."""

    version = "national-elo-v1"

    def __init__(
        self, windows: list[tuple[date, date]], home_advantage: float = HOME_ADVANTAGE
    ) -> None:
        self.home_advantage = home_advantage
        self.params: dict[str, float | str] = {
            "home_advantage": home_advantage,
            "k": "eloratings.net: 20/30/40/50/60 by match_weight()",
            "g": "eloratings.net goal-difference multiplier",
        }
        self.ratings: dict[str, float] = {}
        self.logit = TournamentLogit(windows)

    def rating(self, team: str) -> float:
        return self.ratings.setdefault(team, 1500.0)

    def difference(self, team_a: str, team_b: str, home: str | None) -> float:
        bonus = (
            self.home_advantage
            if home == team_a
            else -self.home_advantage
            if home == team_b
            else 0.0
        )
        return self.rating(team_a) - self.rating(team_b) + bonus

    def observe(self, m: NationalMatch) -> None:
        if m.awarded:
            return
        home = None if m.neutral else m.home_team_id
        d = self.difference(m.home_team_id, m.away_team_id, home)
        result = outcome(m.home_score, m.away_score)
        w = {"H": 1.0, "D": 0.5, "A": 0.0}[result]
        we = 1 / (1 + 10 ** (-d / 400))
        change = (
            match_weight(m.tournament) * goal_multiplier(m.home_score - m.away_score) * (w - we)
        )
        self.ratings[m.home_team_id] = self.rating(m.home_team_id) + change
        self.ratings[m.away_team_id] = self.rating(m.away_team_id) - change
        if m.finals is not None and m.score_90_reliable:
            assert m.home_score_90 is not None and m.away_score_90 is not None
            result_90 = outcome(m.home_score_90, m.away_score_90)
            self.logit.add(m.match_date, d, OUTCOMES.index(result_90))

    def predict(self, team_a: str, team_b: str, home: str | None, as_of: date) -> Probs | None:
        return self.logit.predict(as_of, self.difference(team_a, team_b, home))


class NaiveTournamentBenchmark:
    """H/D/A base rates from every earlier WC/EURO finals match with a reliable
    90-minute score, split by whether the host plays: `neutral` is false only
    in the host's own matches, where the host is always `home_team`
    (docs/data-sources.md)."""

    version = "naive-tournament-v1"

    def __init__(self) -> None:
        self.params: dict[str, float | str] = {}
        self.counts: dict[bool, Counter[str]] = {True: Counter(), False: Counter()}  # host playing

    def observe(self, m: NationalMatch) -> None:
        if m.finals is not None and m.score_90_reliable:
            assert m.home_score_90 is not None and m.away_score_90 is not None
            self.counts[not m.neutral][outcome(m.home_score_90, m.away_score_90)] += 1

    def predict(self, neutral: bool) -> Probs | None:
        counts = self.counts[not neutral]
        n = counts.total()
        if not n:
            return None
        return (counts["H"] / n, counts["D"] / n, counts["A"] / n)


class EloRatingsBenchmark:
    """eloratings.net's published pre-match ratings through the same kind of
    ordered logit as national-elo-v1, fit on the same matches
    (docs/tournament-spec.md, Benchmarks)."""

    version = "eloratings-v1"

    def __init__(
        self, windows: list[tuple[date, date]], home_advantage: float = HOME_ADVANTAGE
    ) -> None:
        self.home_advantage = home_advantage
        self.params: dict[str, float | str] = {"home_advantage": home_advantage}
        self.logit = TournamentLogit(windows)

    def _gap(self, m: NationalMatch) -> float | None:
        if m.elo_home_rating_pre is None or m.elo_away_rating_pre is None:
            return None
        bonus = 0.0 if m.neutral else self.home_advantage
        return m.elo_home_rating_pre - m.elo_away_rating_pre + bonus

    def observe(self, m: NationalMatch) -> None:
        gap = self._gap(m)
        if gap is not None and m.finals is not None and m.score_90_reliable:
            assert m.home_score_90 is not None and m.away_score_90 is not None
            result_90 = outcome(m.home_score_90, m.away_score_90)
            self.logit.add(m.match_date, gap, OUTCOMES.index(result_90))

    def predict(self, m: NationalMatch) -> Probs | None:
        gap = self._gap(m)
        return None if gap is None else self.logit.predict(m.match_date, gap)


@lru_cache(maxsize=32)
def _built(as_of: date, warehouse: Path = WAREHOUSE) -> NationalElo:
    matches = load(warehouse, before=as_of)
    model = NationalElo(tournament_windows(matches))
    for m in matches:
        model.observe(m)
    return model


@lru_cache(maxsize=32)
def eloratings_benchmark_at(as_of: date, warehouse: Path = WAREHOUSE) -> EloRatingsBenchmark:
    """eloratings-v1, walk-forward built and its ordered logit fit on every match strictly
    before `as_of`, the same discipline as `_built` (national-elo-v1): used by
    `tournament_run.py` to bind eloratings-v1 to the simulator."""
    matches = load(warehouse, before=as_of)
    model = EloRatingsBenchmark(tournament_windows(matches))
    for m in matches:
        model.observe(m)
    return model


def match_probs(
    team_a: str,
    team_b: str,
    home_team_or_none: str | None,
    as_of: date,
    warehouse: Path = WAREHOUSE,
) -> Probs | None:
    """national-elo-v1's interface for the tournament simulator.

    `team_a`, `team_b`: team_id (dbt/seeds/team_names.csv). `home_team_or_none`:
    whichever of the two has home advantage (a real venue, hosts at their own
    tournament included), or None at a neutral venue. `as_of`: only matches with
    match_date strictly before `as_of` are known (walk-forward).

    Returns 90-minute `(P(team_a), P(draw), P(team_b))`. `team_a` fills the
    'home' slot of the output regardless of `home_team_or_none`
    (docs/tournament-spec.md, Targets: "home" is the team listed first) so log
    loss and RPS do not depend on which team is passed first. None if the model
    has no ordered-logit fit yet (`as_of` before any finals history).

    Replaying ratings from 1872 is the expensive part; results are cached per
    `as_of` (results are historical facts, the same for every call at that
    `as_of`), so a simulator asking many matchups at one `as_of` (a Monte Carlo
    run of a single tournament) pays for it once. `as_of` is capped at the end
    of development by `load()` until a review authorizes scoring later periods.
    """
    return _built(as_of, warehouse).predict(team_a, team_b, home_team_or_none, as_of)
