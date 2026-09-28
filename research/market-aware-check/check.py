"""Spec question 2b: does a market-aware model beat the market alone?

market-elo-v1 and market-dc-v1 against market-consensus-v1, paired over the
matches all three predicted; 95% intervals from a bootstrap over matchdays
(the prediction's date), 1,000 draws. Then the fitted weights per season, and
whether disagreement between model and market carries information.
Development and validation seasons, stored predictions; run after `mise run backtest`.

Run: uv run research/market-aware-check/check.py
"""

import numpy as np
import pandas as pd

from football_forecasting.market_aware import MARKET, VARIANTS, inputs, walk_forward
from football_forecasting.report import Selection, bootstrap, connect, query

MODELS = (MARKET, *VARIANTS)
con = connect()


def paired(sel: Selection) -> None:
    df = query(
        con,
        """
        select period, horizon, match_id, prediction_as_of::date as day, model_version as model,
            -ln(p_result) as loss
        from scored
        """,
        sel,
    ).df()
    wide = df.pivot_table(
        index=["period", "horizon", "match_id", "day"], columns="model", values="loss"
    ).reset_index()
    for (period, horizon), g in wide.groupby(["period", "horizon"]):
        cells = [f"{g[MARKET].mean():.4f}"]
        for model in VARIANTS:
            diff = (g[model] - g[MARKET]).to_numpy()
            lo, hi = bootstrap(diff, g["day"].to_numpy())
            cells.append(f"{diff.mean():+.4f} ({lo:+.4f}, {hi:+.4f})")
        print(f"| {period} | {horizon} | {len(g):,} | " + " | ".join(cells) + " |")


header = (
    "| Period | Horizon | n | Market | market-elo - Market | market-dc - Market |\n"
    "|---|---|---|---|---|---|"
)
print("## Log loss differences, all matches\n\n" + header)
paired(Selection(MODELS))
print("\n## Without pre_timing_uncertain\n\n" + header)
paired(Selection(MODELS, certain_only=True))

# Refit exactly as market_aware does, to show the weights
print("\n## Fitted weights per season (a: market, b: model, c: intercepts)\n")
for version, model in VARIANTS.items():
    _, w = walk_forward(inputs(con, model))
    print(f"### {version}\n\n| horizon | season | n fit | a | b | c_home | c_draw |")
    print("|---|---|---|---|---|---|---|")
    for r in w.itertuples():
        print(
            f"| {r.horizon} | {r.season} | {r.n_fit:,} | {r.market:.3f} | {r.model:+.3f} "
            f"| {r.c_home:+.3f} | {r.c_draw:+.3f} |"
        )
    print()

# Disagreement: bin p_model - p_market for the home outcome
print("## Disagreement on the home win, model minus market\n")
edges = [-1, -0.10, -0.06, -0.03, -0.01, 0.01, 0.03, 0.06, 0.10, 1]
labels = ["< -10", "-10 to -6", "-6 to -3", "-3 to -1", "-1 to +1", "+1 to +3", "+3 to +6",
          "+6 to +10", "> +10"]  # fmt: skip
for certain_only in (False, True):
    for model, short in [("elo-v1", "Elo"), ("dixon-coles-v1", "DC")]:
        df = query(
            con,
            """
            select period, horizon, match_id, model_version, p_home, (result = 'H')::int as hit
            from scored
            """,
            Selection((MARKET, model), certain_only=certain_only),
        ).df()
        wide = df.pivot_table(
            index=["period", "horizon", "match_id", "hit"], columns="model_version", values="p_home"
        ).reset_index()
        wide["bin"] = pd.cut(wide[model] - wide[MARKET], edges, labels=labels)
        tag = " (without pre_timing_uncertain)" if certain_only else ""
        print(f"### {short}{tag}\n")
        print("| period | horizon | gap, points | n | market | model | observed | obs - market |")
        print("|---|---|---|---|---|---|---|---|")
        for (period, horizon, b), g in wide.groupby(["period", "horizon", "bin"], observed=True):
            mk, obs = g[MARKET].mean(), g["hit"].mean()
            se = np.sqrt(obs * (1 - obs) / len(g))
            print(
                f"| {period} | {horizon} | {b} | {len(g):,} | {mk:.3f} | {g[model].mean():.3f} "
                f"| {obs:.3f} | {obs - mk:+.3f} ± {1.96 * se:.3f} |"
            )
        # slope of (observed - market) on (model - market), matches pooled per period, horizon
        for (period, horizon), g in wide.groupby(["period", "horizon"]):
            x, r = (g[model] - g[MARKET]).to_numpy(), (g["hit"] - g[MARKET]).to_numpy()
            print(f"\n{period} {horizon}: slope {np.polyfit(x, r, 1)[0]:+.3f}", end="")
        print("\n")
