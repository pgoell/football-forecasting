"""Phase 4: does a feature model beat the base models, and does it add to the market?

For each new model: log loss minus naive, Elo, Dixon-Coles and the market,
paired over the matches all of them predicted, then its market-aware blend
minus the market, the blend's weight on the model per season, and the slope of
(observed - market) on (model - market) for the home win. A model that starts
late (xg-dc-v1, 2014/15) narrows every comparison to its seasons. 95% intervals from a
bootstrap over matchdays (report.bootstrap). Development and validation seasons,
stored predictions; run after `mise run backtest`.

Run: uv run research/phase4-check/check.py shots-dc-v1
"""

import sys

import numpy as np

from football_forecasting.market_aware import MARKET, VARIANTS, inputs, walk_forward
from football_forecasting.report import Selection, bootstrap, connect, query

BASE = ("naive-v1", "elo-v1", "dixon-coles-v1", MARKET)
con = connect()


def losses(models: tuple[str, ...], certain_only: bool = False):
    """Log loss per match, wide by model, on the matches all `models` predicted."""
    df = query(
        con,
        """
        select period, horizon, match_id, prediction_as_of::date as day, model_version as model,
            -ln(p_result) as loss
        from scored
        """,
        Selection(models, certain_only=certain_only),
    ).df()
    return df.pivot_table(
        index=["period", "horizon", "match_id", "day"], columns="model", values="loss"
    ).reset_index()


def paired(
    model: str, refs: tuple[str, ...], certain_only: bool = False, also: tuple[str, ...] = ()
) -> None:
    """`model` minus each of `refs`; `also` only narrows the matches to those it predicted."""
    wide = losses((model, *refs, *also), certain_only)
    print(f"| Period | Horizon | n | {model} | " + " | ".join(f"− {r}" for r in refs) + " |")
    print("|---|---|---|---|" + "---|" * len(refs))
    for (period, horizon), g in wide.groupby(["period", "horizon"], sort=False):
        cells = [f"{g[model].mean():.4f}"]
        for ref in refs:
            diff = (g[model] - g[ref]).to_numpy()
            lo, hi = bootstrap(diff, g["day"].to_numpy())
            cells.append(f"{diff.mean():+.4f} ({lo:+.4f}, {hi:+.4f})")
        print(f"| {period} | {horizon} | {len(g):,} | " + " | ".join(cells) + " |")


def slope(model: str) -> None:
    df = query(
        con,
        "select period, horizon, match_id, model_version, p_home, (result = 'H')::int as hit "
        "from scored",
        Selection((MARKET, model)),
    ).df()
    wide = df.pivot_table(
        index=["period", "horizon", "match_id", "hit"], columns="model_version", values="p_home"
    ).reset_index()
    print("| Period | Horizon | slope |\n|---|---|---|")
    for (period, horizon), g in wide.groupby(["period", "horizon"], sort=False):
        x = (g[model] - g[MARKET]).to_numpy()
        r = (g["hit"] - g[MARKET]).to_numpy()
        b = np.polyfit(x, r, 1)[0]
        se = np.sqrt(((r - r.mean()) ** 2).mean() / ((x - x.mean()) ** 2).sum())
        print(f"| {period} | {horizon} | {b:+.3f} ± {1.96 * se:.3f} |")


for model in sys.argv[1:]:
    blend = next(v for v, m in VARIANTS.items() if m == model)
    print(f"# {model}\n\n## Log loss and differences, all matches\n")
    paired(model, BASE)
    print("\n## Without pre_timing_uncertain\n")
    paired(model, BASE, certain_only=True)
    print(f"\n## {blend} minus the market\n")
    paired(blend, (MARKET,))
    print("\n## Without pre_timing_uncertain\n")
    paired(blend, (MARKET,), certain_only=True)
    print(f"\n## For comparison, market-dc-v1 minus the market, same matches as {blend}\n")
    paired("market-dc-v1", (MARKET,), also=(blend,))
    print(f"\n## {blend}: fitted weights (a: market, b: model)\n")
    _, w = walk_forward(inputs(con, model))
    print("| horizon | season | n fit | a | b | c_home | c_draw |\n|---|---|---|---|---|---|---|")
    for r in w.itertuples():
        print(
            f"| {r.horizon} | {r.season} | {r.n_fit:,} | {r.market:.3f} | {r.model:+.3f} "
            f"| {r.c_home:+.3f} | {r.c_draw:+.3f} |"
        )
    print("\n## Slope of (observed - market) on (model - market), home win\n")
    slope(model)
    print()
