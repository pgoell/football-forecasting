"""Forecast models. The engine feeds each one played matches through observe() and asks
for P(H), P(D), P(A) through predict(); a model sees nothing else."""

import math
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Protocol

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import poisson

from football_forecasting.data import Fixture, Match, Odds

Probs = tuple[float, float, float]
Row = tuple[str, str, str, int, int, float, tuple[int, int] | None]
OUTCOMES = ("H", "D", "A")


class Model(Protocol):
    version: str
    params: dict[str, float]

    def observe(self, match: Match) -> None: ...

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None: ...


class Naive:
    """League base rates of H, D and A from all earlier seasons."""

    version = "naive-v1"

    def __init__(self) -> None:
        self.params: dict[str, float] = {}
        self.counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    def observe(self, match: Match) -> None:
        self.counts[match.fixture.league, match.fixture.season][match.result] += 1

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

    def __init__(self) -> None:
        self.params: dict[str, float] = {}

    def observe(self, match: Match) -> None:
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
        self.params: dict[str, float] = {
            "k": k,
            "home_advantage": home_advantage,
            "promoted_rating": promoted_rating,
        }
        self.ratings: dict[tuple[str, str], float] = {}
        self.teams: dict[tuple[str, str], set[str]] = defaultdict(set)  # (league, season)
        self.history: list[tuple[float, int]] = []  # (rating difference, outcome index)
        self.fit_season = ""
        self.logit = np.zeros(3)

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

    def observe(self, match: Match) -> None:
        fixture, result = match.fixture, match.result
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
            self.logit = fit_ordered_logit(self.history)
            self.fit_season = fixture.season
        return ordered_logit(self.logit, self.difference(fixture) / 400)


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


class Poisson:
    """Home and away goals as independent Poisson, fitted per league by maximum
    likelihood on the current and two previous seasons:

        log(home rate) = mean + home + attack[home team] + defence[away team]
        log(away rate) = mean + attack[away team] + defence[home team]

    Refit before a prediction whenever the league has new results. A penalty
    (attack - target)^2 / (2 sd^2), and the same for defence, pulls each team
    toward target 0, or toward the promoted-team prior for a team not in the
    league the season before. Prior and sd come from the warm-up seasons only
    (research/goal-model-prior/). H, D and A come from the score grid up to
    10 goals a side."""

    version = "poisson-v1"
    xi = 0.0  # time decay per day
    low_score = False  # Dixon-Coles correction of 0-0, 1-0, 0-1 and 1-1

    def __init__(
        self, promoted_attack: float = -0.32, promoted_defence: float = 0.25, sd: float = 0.24
    ) -> None:
        self.promoted = (promoted_attack, promoted_defence)
        self.sd = sd
        self.params: dict[str, float] = {
            "seasons": 3,
            "xi": self.xi,
            "promoted_attack": promoted_attack,
            "promoted_defence": promoted_defence,
            "sd": sd,
        }
        # (league) -> rows of (season, home, away, home goals, away goals, result_at in days,
        # shots on target or None)
        self.results: dict[str, list[Row]] = defaultdict(list)
        self.teams: dict[tuple[str, str], set[str]] = defaultdict(set)  # (league, season)
        self.fits: dict[str, tuple[int, str, dict[str, int], np.ndarray]] = {}

    def observe(self, match: Match) -> None:
        f = match.fixture
        days = match.result_at.timestamp() / 86400
        self.results[f.league].append(
            (f.season, f.home_team, f.away_team, *match.goals, days, match.shots_on_target)
        )
        self.teams[f.league, f.season] |= {f.home_team, f.away_team}

    def target(self, league: str, season: str, team: str) -> tuple[float, float]:
        earlier = [s for (lg, s) in self.teams if lg == league and s < season]
        return (0.0, 0.0) if earlier and team in self.teams[league, max(earlier)] else self.promoted

    def fit(self, fixture: Fixture, as_of: datetime) -> tuple[dict[str, int], np.ndarray]:
        league, season = fixture.league, fixture.season
        results = self.results[league]
        cached = self.fits.get(league)
        if cached and cached[:2] == (len(results), season):
            return cached[2], cached[3]
        seasons = sorted({s for (lg, s) in self.teams if lg == league and s < season})[-2:]
        rows = [r for r in results if r[0] in seasons or r[0] == season]
        teams = {t: i for i, t in enumerate(sorted({t for r in rows for t in r[1:3]}))}
        target = np.array([self.target(league, season, t) for t in teams]).T.ravel()
        days = as_of.timestamp() / 86400
        params = fit_goals(
            np.array([teams[r[1]] for r in rows]),
            np.array([teams[r[2]] for r in rows]),
            np.array([r[3] for r in rows]),
            np.array([r[4] for r in rows]),
            np.exp(-self.xi * (days - np.array([r[5] for r in rows]))),
            target,
            self.sd,
            self.low_score,
            self.counts(rows),
        )
        self.fits[league] = (len(results), season, teams, params)
        return teams, params

    def counts(self, rows: list[Row]) -> tuple[np.ndarray, np.ndarray] | None:
        """What the rates are fitted to, home and away; None for the goals."""
        return None

    def predict(
        self, fixture: Fixture, horizon: str, as_of: datetime, odds: list[Odds]
    ) -> Probs | None:
        if not self.results[fixture.league]:
            return None
        teams, params = self.fit(fixture, as_of)
        mean, home, rho = params[:3]
        n = len(teams)

        def strength(team: str) -> tuple[float, float]:
            if team in teams:
                return params[3 + teams[team]], params[3 + n + teams[team]]
            # no match in the window: the penalty alone sets it, at its target
            return self.target(fixture.league, fixture.season, team)

        home_attack, home_defence = strength(fixture.home_team)
        away_attack, away_defence = strength(fixture.away_team)
        return score_probs(
            math.exp(mean + home + home_attack + away_defence),
            math.exp(mean + away_attack + home_defence),
            rho,
        )


class DixonColes(Poisson):
    """Poisson plus the Dixon-Coles correction of low scores (rho, fitted) and
    exponential time decay of older matches, weight exp(-xi * age in days).
    xi = 0.0065 per half week, Dixon and Coles (1997), set by hand."""

    version = "dixon-coles-v1"
    xi = 0.0065 / 3.5
    low_score = True


class ShotsDixonColes(DixonColes):
    """Dixon-Coles with the rates fitted to a blend of goals and shots on target:

        count = (1 - w) * goals + w * c * shots on target

    c is the league's goals per shot on target in the fit window, so both parts
    count goals. w = 1 fits on shots on target alone, w = 0 is dixon-coles-v1.
    Shots on target are the more stable signal of how well a team plays; goals
    add finishing and luck. Matches without shots on target (D1 2002/03 to
    2005/06) count their goals. The low-score factor still uses the score.
    w chosen on development seasons (research/shots-weight/)."""

    version = "shots-dc-v1"

    def __init__(self, shots_weight: float = 0.25) -> None:
        super().__init__()
        self.w = shots_weight
        self.params["shots_weight"] = shots_weight

    def counts(self, rows: list[Row]) -> tuple[np.ndarray, np.ndarray]:
        goals = np.array([r[3:5] for r in rows], dtype=float)
        known = np.array([r[6] is not None for r in rows])
        shots = np.array([r[6] or (0, 0) for r in rows], dtype=float)
        c = goals[known].sum() / max(shots[known].sum(), 1)
        blend = np.where(known[:, None], (1 - self.w) * goals + self.w * c * shots, goals)
        return blend[:, 0], blend[:, 1]


def tau(hg: np.ndarray, ag: np.ndarray, mu, nu, rho):
    """Dixon-Coles factor on the Poisson probability of each score, with its
    derivatives by log(mu), log(nu) and rho."""
    z00, z01 = ((hg == 0) & (ag == 0)) * 1.0, ((hg == 0) & (ag == 1)) * 1.0
    z10, z11 = ((hg == 1) & (ag == 0)) * 1.0, ((hg == 1) & (ag == 1)) * 1.0
    t = 1 - z00 * mu * nu * rho + z01 * mu * rho + z10 * nu * rho - z11 * rho
    return (
        np.clip(t, 1e-9, None),
        rho * mu * (z01 - z00 * nu),
        rho * nu * (z10 - z00 * mu),
        -z00 * mu * nu + z01 * mu + z10 * nu - z11,
    )


def fit_goals(
    home: np.ndarray,
    away: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    target: np.ndarray,
    sd: float,
    low_score: bool,
    counts: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """Penalized weighted maximum likelihood; returns (mean, home, rho, attack..., defence...).
    Teams are indices into target = (attack targets..., defence targets...). The
    rates fit `counts` (home, away), goals if None; the low-score factor uses goals."""
    n = len(target) // 2
    home_counts, away_counts = counts if counts is not None else (home_goals, away_goals)

    def loss(params: np.ndarray) -> tuple[float, np.ndarray]:
        mean, home_adv, rho = params[:3]
        attack, defence = params[3 : 3 + n], params[3 + n :]
        log_mu = mean + home_adv + attack[home] + defence[away]
        log_nu = mean + attack[away] + defence[home]
        mu, nu = np.exp(log_mu), np.exp(log_nu)
        ll = home_counts * log_mu - mu + away_counts * log_nu - nu
        d_mu, d_nu = home_counts - mu, away_counts - nu
        d_rho = np.zeros_like(mu)
        if low_score:
            t, t_mu, t_nu, t_rho = tau(home_goals, away_goals, mu, nu, rho)
            ll = ll + np.log(t)
            d_mu, d_nu, d_rho = d_mu + t_mu / t, d_nu + t_nu / t, t_rho / t
        wm, wn = weights * d_mu, weights * d_nu
        grad = -np.concatenate(
            [
                [wm.sum() + wn.sum(), wm.sum(), (weights * d_rho).sum()],
                np.bincount(home, wm, n) + np.bincount(away, wn, n),
                np.bincount(away, wm, n) + np.bincount(home, wn, n),
            ]
        )
        off = params[3:] - target
        grad[3:] += off / sd**2
        return -(weights * ll).sum() + (off**2).sum() / (2 * sd**2), grad

    x0 = np.concatenate([[math.log(max(home_counts.mean(), 0.1)), 0.25, 0.0], target])
    bounds = [(None, None), (None, None), (-0.3, 0.3) if low_score else (0, 0)]
    bounds += [(None, None)] * (2 * n)
    return minimize(loss, x0, jac=True, method="L-BFGS-B", bounds=bounds).x


def score_probs(mu: float, nu: float, rho: float, cap: int = 10) -> Probs:
    """H, D and A from the score grid up to `cap` goals a side, renormalized."""
    goals = np.arange(cap + 1)
    grid = np.outer(poisson.pmf(goals, mu), poisson.pmf(goals, nu))
    home_goals, away_goals = np.indices((2, 2))
    grid[:2, :2] *= np.clip(tau(home_goals, away_goals, mu, nu, rho)[0], 0, None)
    grid /= grid.sum()
    return (float(np.tril(grid, -1).sum()), float(np.trace(grid)), float(np.triu(grid, 1).sum()))
