"""Where the league levels of elo-country-v1 and dixon-coles-country-v1 settle.

Warm-up seasons only (2000/01 to 2004/05): feeds the models every warm-up
match and prints, after each season, the mean Elo rating per league and the
Dixon-Coles attack and defence levels per league (0 in the top league).

Run: uv run research/country-levels/levels.py
"""

from football_forecasting.data import FIRST_DEVELOPMENT_SEASON, leagues, load
from football_forecasting.models import DixonColesCountry, EloCountry

known = leagues()
matches, _ = load()
warm_up = sorted(
    (m for m in matches if m.fixture.season < FIRST_DEVELOPMENT_SEASON), key=lambda m: m.result_at
)
elo, dc = EloCountry(known), DixonColesCountry(known)
seasons = sorted({m.fixture.season for m in warm_up})
print("| After season | League | Elo mean | DC attack level | DC defence level |")
print("|---|---|---|---|---|")
for season in seasons:
    for m in (m for m in warm_up if m.fixture.season == season):
        elo.observe(m)
        dc.observe(m)
    last = [m for m in warm_up if m.fixture.season == season][-1]
    for country in ("England", "Germany"):
        ours = sorted((lg for lg in known if known[lg][0] == country), key=lambda lg: known[lg][1])
        _, _, params = dc.fit_country(country, season, last.result_at)
        k = len(ours)
        attack = [0.0, *params[1 + 2 * k : 3 * k]]
        defence = [0.0, *params[3 * k : 4 * k - 1]]
        for i, lg in enumerate(ours):
            teams = elo.teams[lg, season]
            mean = sum(elo.ratings[country, t] for t in teams) / len(teams)
            print(f"| {season} | {lg} | {mean:.0f} | {attack[i]:+.2f} | {defence[i]:+.2f} |")
