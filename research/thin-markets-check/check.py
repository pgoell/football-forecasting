"""Thin markets: do our models add to the market in D2, E1 and E2?

The pre-registered test (docs/experiment-spec.md, change log): per league and
horizon on validation, blend log loss minus market log loss, paired over the
matches both predicted, bootstrap over matchdays with 10,000 draws; pass if the
99% interval lies wholly below 0. The blend tested is the one whose base model
has the lower development log loss at `pre`, the three leagues together.

Also: log loss of every model per league, period and horizon on the matches all
of them predicted, and the bookmaker margin per league. Development and
validation seasons, stored predictions; run after `mise run backtest`.

Run: uv run research/thin-markets-check/check.py
"""

import numpy as np

from football_forecasting.market_aware import MARKET
from football_forecasting.report import Selection, bootstrap, connect, query

LEAGUES = ("D2", "E1", "E2")
BASES = {
    "elo-country-v1": "market-elo-country-v1",
    "dixon-coles-country-v1": "market-dc-country-v1",
}
MODELS = ("naive-v1", *BASES, MARKET, *BASES.values())
con = connect()


def losses(models: tuple[str, ...], certain_only: bool = False):
    """Log loss per match, wide by model, on the matches all `models` predicted."""
    df = query(
        con,
        """
        select league, period, horizon, match_id, prediction_as_of::date as day,
            model_version as model, -ln(p_result) as loss
        from scored
        """,
        Selection(models, certain_only=certain_only),
    ).df()
    df = df[df["league"].isin(LEAGUES)]
    return df.pivot_table(
        index=["league", "period", "horizon", "match_id", "day"], columns="model", values="loss"
    ).reset_index()


print("## Log loss, matches all models predicted\n")
wide = losses(MODELS)
print("| League | Period | Horizon | n | " + " | ".join(MODELS) + " |")
print("|---|---|---|---|" + "---|" * len(MODELS))
for (league, period, horizon), g in wide.groupby(["league", "period", "horizon"]):
    cells = " | ".join(f"{g[m].mean():.4f}" for m in MODELS)
    print(f"| {league} | {period} | {horizon} | {len(g):,} | {cells} |")

# Which blend is tested: base model with the lower development log loss at pre,
# three leagues together, on the matches both base models and the market predicted
dev = losses((*BASES, MARKET))
dev = dev[(dev["period"] == "development") & (dev["horizon"] == "pre")]
base_loss = {b: dev[b].mean() for b in BASES}
best = min(base_loss, key=base_loss.__getitem__)
blend = BASES[best]
print(f"\n## Base model choice (development, pre, n {len(dev):,})\n")
for b, v in base_loss.items():
    print(f"- {b}: {v:.4f}")
print(f"- tested blend: {blend}")

for certain_only in (False, True):
    title = "without pre_timing_uncertain" if certain_only else "all matches"
    print(f"\n## Criterion 2b, {title}: blend minus market, 99% interval, 10,000 draws\n")
    print("| League | Period | Horizon | n | Market | " + " | ".join(BASES.values()) + " |")
    print("|---|---|---|---|---|---|---|")
    pairs = losses((MARKET, *BASES.values()), certain_only)
    for (league, period, horizon), g in pairs.groupby(["league", "period", "horizon"]):
        cells = [f"{g[MARKET].mean():.4f}"]
        for b in BASES.values():
            diff = (g[b] - g[MARKET]).to_numpy()
            lo, hi = bootstrap(diff, g["day"].to_numpy(), draws=10_000, level=0.99)
            mark = " **pass**" if hi < 0 and period == "validation" and b == blend else ""
            cells.append(f"{diff.mean():+.4f} ({lo:+.4f}, {hi:+.4f}){mark}")
        print(f"| {league} | {period} | {horizon} | {len(g):,} | " + " | ".join(cells) + " |")

print("\n## Bookmaker margin (overround - 1), validation, mean per match\n")
margins = con.execute(
    """
    select m.league, o.moment, o.bookmaker, avg(o.overround - 1) as margin, count(*) as n
    from wh.int_odds as o
    inner join wh.int_matches as m using (match_id)
    inner join wh.bookmakers as b on o.bookmaker = b.code
    where m.season >= '1920' and m.season < '2324' and o.is_reliable and not b.is_aggregate
    group by all
    """
).df()
table = margins.pivot_table(index=["moment", "bookmaker"], columns="league", values="margin")
print(table.map(lambda v: f"{100 * v:.1f}%" if not np.isnan(v) else "").to_markdown())
