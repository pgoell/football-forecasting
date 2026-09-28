"""Promoted-team prior and penalty sd for the goal models, from warm-up
seasons (2000/01 to 2004/05) only.

Fits each warm-up league season on its own, almost without penalty, with
attack and defence centred on the league. The prior is the mean attack and
defence of the teams relegated at the end of a season, so promoted teams
enter at the level of the teams they replace (as for elo-v1). sd is the
spread of attack and defence across all team seasons.
Run: uv run research/goal-model-prior/prior.py
"""

from collections import defaultdict

import numpy as np

from football_forecasting.data import FIRST_DEVELOPMENT_SEASON, load
from football_forecasting.models import fit_goals

matches, _ = load()
by_season = defaultdict(list)
for m in matches:
    if m.fixture.season < FIRST_DEVELOPMENT_SEASON:
        by_season[m.fixture.league, m.fixture.season].append(m)

strengths, relegated = [], []
for (league, season), ms in sorted(by_season.items()):
    teams = {t: i for i, t in enumerate(sorted({m.fixture.home_team for m in ms}))}
    n = len(teams)
    params = fit_goals(
        np.array([teams[m.fixture.home_team] for m in ms]),
        np.array([teams[m.fixture.away_team] for m in ms]),
        np.array([m.goals[0] for m in ms]),
        np.array([m.goals[1] for m in ms]),
        np.ones(len(ms)),
        np.zeros(2 * n),
        10.0,
        False,
    )
    attack, defence = params[3 : 3 + n], params[3 + n :]
    attack, defence = attack - attack.mean(), defence - defence.mean()
    strengths += [*attack, *defence]
    following = by_season.get((league, f"{season[2:]}{int(season[2:]) + 1:02d}"))
    if following:
        stay = {m.fixture.home_team for m in following}
        relegated += [(attack[i], defence[i]) for t, i in teams.items() if t not in stay]

prior = np.mean(relegated, axis=0)
print(
    f"{len(relegated)} relegations, attack {prior[0]:+.3f}, defence {prior[1]:+.3f}, "
    f"sd {np.std(strengths):.3f}"
)
