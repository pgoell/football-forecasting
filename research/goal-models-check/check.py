"""Phase 3 exit check: goal models against Elo and the market, and where
their calibration is poor. Development and validation seasons, stored
predictions; run after `mise run backtest`.

Differences are paired over the matches all five models predicted; 95%
intervals from a bootstrap over matchdays (the prediction's date), 1,000 draws.
Run: uv run research/goal-models-check/check.py
"""

import numpy as np

from football_forecasting.report import MODELS, Selection, calibration, connect, query

rng = np.random.default_rng(0)
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
    for (period, horizon), g in wide.groupby(["period", "horizon"], sort=False):
        days = g["day"].factorize()[0]
        draws = rng.integers(0, days.max() + 1, (1000, days.max() + 1))
        counts = np.stack([np.bincount(d, minlength=days.max() + 1) for d in draws])[:, days]
        cells = []
        for model, ref in [
            ("poisson-v1", "elo-v1"),
            ("dixon-coles-v1", "elo-v1"),
            ("dixon-coles-v1", "poisson-v1"),
            ("dixon-coles-v1", "market-consensus-v1"),
        ]:
            diff = (g[model] - g[ref]).to_numpy()
            boot = counts @ diff / counts.sum(axis=1)
            lo, hi = np.percentile(boot, [2.5, 97.5])
            cells.append(f"{diff.mean():+.4f} ({lo:+.4f}, {hi:+.4f})")
        print(f"| {period} | {horizon} | {len(g):,} | " + " | ".join(cells) + " |")


header = (
    "| Period | Horizon | n | Poisson - Elo | DC - Elo | DC - Poisson | DC - Market |\n"
    "|---|---|---|---|---|---|---|"
)
print("## Log loss differences, all matches\n\n" + header)
paired(Selection(MODELS))
print("\n## Without pre_timing_uncertain\n\n" + header)
paired(Selection(MODELS, certain_only=True))

# Mean forecast against observed rate, per outcome, and for draws per bin
print("\n## Calibration, development and validation, pre\n")
cal = calibration(con, Selection(MODELS, horizon="pre"), bins=10).df()
cal["hits"] = cal["observed"] * cal["n"]
cal["p_sum"] = cal["forecast"] * cal["n"]
overall = cal.groupby(["model", "outcome"])[["n", "hits", "p_sum"]].sum()
print("| model | outcome | forecast | observed |\n|---|---|---|---|")
for (model, outcome), r in overall.iterrows():
    print(f"| {model} | {outcome} | {r.p_sum / r.n:.3f} | {r.hits / r.n:.3f} |")
print("\n| model | outcome | bin | n | forecast | observed |\n|---|---|---|---|---|---|")
for r in cal[cal["n"] >= 100].itertuples():
    print(f"| {r.model} | {r.outcome} | {r.bin:.0f} | {r.n} | {r.forecast:.3f} | {r.observed:.3f} |")
