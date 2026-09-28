"""Forecast models. The engine feeds each one results through observe() and asks
for P(H), P(D), P(A) through predict(); a model sees nothing else."""

import math
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Protocol

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from football_forecasting.data import Fixture, Odds

Probs = tuple[float, float, float]
OUTCOMES = ("H", "D", "A")


class Model(Protocol):
    version: str

    def observe(self, fixture: Fixture, result: str) -> None: ...

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None: ...


class Naive:
    """League base rates of H, D and A from all earlier seasons."""

    version = "naive-v1"

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    def observe(self, fixture: Fixture, result: str) -> None:
        self.counts[fixture.league, fixture.season][result] += 1

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None:
        total: Counter[str] = Counter()
        for (league, season), counts in self.counts.items():
            if league == fixture.league and season < fixture.season:
                total += counts
        n = total.total()
        if not n:
            return None
        return (total["H"] / n, total["D"] / n, total["A"] / n)


class MarketConsensus:
    """Median of devigged probabilities across reliable, non-aggregate bookmakers,
    from the odds of the horizon's own moment, renormalized to sum to 1."""

    version = "market-consensus-v1"

    def observe(self, fixture: Fixture, result: str) -> None:
        pass

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None:
        probs = [
            o.probs for o in odds if o.moment == horizon and o.is_reliable and not o.is_aggregate
        ]
        if not probs:
            return None
        h, d, a = (median(p[i] for p in probs) for i in range(3))
        s = h + d + a
        return (h / s, d / s, a / s)


class Elo:
    """Elo ratings, carried across seasons, mapped to H/D/A by an ordered logit
    on the rating difference, refit on all earlier results at each new season.

    Every team starts at 1500 in its league's first season. A team that was not
    in the league the season before gets `promoted_rating`, set from the warm-up
    seasons only (docs/experiment-log.md)."""

    version = "elo-v1"

    def __init__(
        self, k: float = 20, home_advantage: float = 60, promoted_rating: float = 1400
    ) -> None:
        self.k = k
        self.home_advantage = home_advantage
        self.promoted_rating = promoted_rating
        self.ratings: dict[tuple[str, str], float] = {}
        self.teams: dict[tuple[str, str], set[str]] = defaultdict(set)  # (league, season)
        self.history: list[tuple[float, int]] = []  # (rating difference, outcome index)
        self.fit_season = ""
        self.params = np.zeros(3)

    def rating(self, fixture: Fixture, team: str) -> float:
        league, season = fixture.league, fixture.season
        if team not in self.teams[league, season]:
            earlier = [s for (lg, s) in self.teams if lg == league and s < season]
            if not earlier:
                self.ratings.setdefault((league, team), 1500.0)
            elif team not in self.teams[league, max(earlier)]:
                self.ratings[league, team] = self.promoted_rating
            self.teams[league, season].add(team)
        return self.ratings[league, team]

    def difference(self, fixture: Fixture) -> float:
        home = self.rating(fixture, fixture.home_team)
        away = self.rating(fixture, fixture.away_team)
        return home - away + self.home_advantage

    def observe(self, fixture: Fixture, result: str) -> None:
        d = self.difference(fixture)
        change = self.k * ({"H": 1.0, "D": 0.5, "A": 0.0}[result] - 1 / (1 + 10 ** (-d / 400)))
        self.ratings[fixture.league, fixture.home_team] += change
        self.ratings[fixture.league, fixture.away_team] -= change
        self.history.append((d, OUTCOMES.index(result)))

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None:
        if not self.history:
            return None
        if fixture.season != self.fit_season:
            self.params = fit_ordered_logit(self.history)
            self.fit_season = fixture.season
        return ordered_logit(self.params, self.difference(fixture) / 400)


def ordered_logit(params: np.ndarray, x: float | np.ndarray) -> Probs:
    """P(A) = s(c1 - bx), P(A or D) = s(c2 - bx), c2 = c1 + exp(g); params = (c1, g, b)."""
    c1, g, b = params
    away = expit(c1 - b * x)
    not_home = expit(c1 + math.exp(g) - b * x)
    return (1 - not_home, not_home - away, away)


def fit_ordered_logit(history: list[tuple[float, int]]) -> np.ndarray:
    x = np.array([d for d, _ in history]) / 400
    y = np.array([o for _, o in history])

    def loss(params: np.ndarray) -> float:
        p = np.stack(ordered_logit(params, x), axis=1)[np.arange(len(y)), y]
        return -np.log(np.clip(p, 1e-12, None)).sum()

    return minimize(loss, np.array([-1.0, 0.0, 1.0]), method="BFGS").x
