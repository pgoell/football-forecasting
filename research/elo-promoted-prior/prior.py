"""Promoted-team Elo prior, from warm-up seasons (2000/01 to 2004/05) only.

The prior is the mean end-of-season rating of the teams relegated in the
warm-up, so promoted teams enter at the level of the teams they replace.
Iterates because promoted teams can be relegated again.
Run: uv run research/elo-promoted-prior/prior.py
"""

from football_forecasting.data import FIRST_DEVELOPMENT_SEASON, load
from football_forecasting.models import Elo

matches, _ = load()
warm_up = sorted(
    (m for m in matches if m.fixture.season < FIRST_DEVELOPMENT_SEASON), key=lambda m: m.result_at
)
prior = 1500.0
for _ in range(20):
    elo = Elo(promoted_rating=prior)
    relegated, end = [], {}
    for m in warm_up:
        elo.observe(m.fixture, m.result)
        end[m.fixture.league, m.fixture.season] = dict(elo.ratings)
    for (league, season), teams in elo.teams.items():
        following = elo.teams.get((league, f"{season[2:]}{int(season[2:]) + 1:02d}"))
        if following:
            relegated += [end[league, season][league, t] for t in teams - following]
    prior = sum(relegated) / len(relegated)
print(f"{len(relegated)} relegations, prior {prior:.1f}")
