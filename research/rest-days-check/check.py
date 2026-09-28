"""Do rest days carry information the market or Dixon-Coles misses?

Development seasons only, pre-match, stored predictions of market-consensus-v1
and dixon-coles-v1. Rest difference = home rest days minus away rest days, each
capped at 8 (a week plus a day; longer breaks are the same to a team). For each
bin: observed home-win rate minus each model's forecast, with a 95% margin.
Then a slope of (observed - forecast) on the rest difference and on the
difference in matches played in the 14 days before.

Run: uv run research/rest-days-check/check.py
"""

import numpy as np

from football_forecasting.report import Selection, connect, query

con = connect()
df = query(
    con,
    """
    select s.match_id, s.model_version as model, s.p_home, s.p_away, (s.result = 'H')::int as hit,
        (s.result = 'A')::int as away_hit,
        least(m.home_rest_days, 8) - least(m.away_rest_days, 8) as rest_diff,
        m.home_matches_14d - m.away_matches_14d as busy_diff
    from scored as s
    inner join wh.int_matches as m using (match_id)
    where m.home_rest_days is not null and m.away_rest_days is not null
    """,
    Selection(("market-consensus-v1", "dixon-coles-v1"), horizon="pre", period="development"),
).df()

for model, g in df.groupby("model"):
    print(f"## {model}, development, pre, n {len(g):,}\n")
    print("| rest diff | n | forecast H | observed H | obs - forecast |")
    print("|---|---|---|---|---|")
    bins = np.clip(g["rest_diff"], -4, 4)
    for b, gb in g.groupby(bins):
        f, o = gb["p_home"].mean(), gb["hit"].mean()
        se = np.sqrt(o * (1 - o) / len(gb))
        print(f"| {b:+d} | {len(gb):,} | {f:.3f} | {o:.3f} | {o - f:+.3f} ± {1.96 * se:.3f} |")
    for col in ("rest_diff", "busy_diff"):
        x = g[col].clip(-4, 4).to_numpy(float)
        for out, p in (("hit", "p_home"), ("away_hit", "p_away")):
            r = (g[out] - g[p]).to_numpy()
            slope, _ = np.polyfit(x, r, 1)
            se = np.sqrt(((r - r.mean()) ** 2).mean() / ((x - x.mean()) ** 2).sum())
            print(f"\n{col} -> {out}: slope {slope:+.4f} per unit ± {1.96 * se:.4f}", end="")
    print("\n")
