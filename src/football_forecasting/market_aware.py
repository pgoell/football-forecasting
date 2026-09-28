"""Market-aware models: the market's forecast combined with one of our models'.

A multinomial logit on the stored predictions of both at the same horizon:

    P(k) proportional to exp(a * log p_market[k] + b * log p_model[k] + c[k]),  c[A] = 0

Before each season it is fitted, unregularized, on all earlier development and
validation seasons, then predicts that season. It reads stored predictions only,
so no base model is refit. b is the weight our model gets; a = 1, b = 0, c = 0
gives the market back.

The `-country-v1` blends (the thin-market experiment, docs/experiment-spec.md
change log) are fitted per league and horizon, the others on all leagues together.

Run after the base models are stored (mise run backtest does both).
"""

import hashlib

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import log_softmax

from football_forecasting.backtest import Prediction, save
from football_forecasting.data import FIRST_DEVELOPMENT_SEASON, FIRST_HOLDOUT_SEASON
from football_forecasting.report import connect

MARKET = "market-consensus-v1"
VARIANTS = {
    "market-elo-v1": "elo-v1",
    "market-dc-v1": "dixon-coles-v1",
    "market-shots-v1": "shots-dc-v1",
    "market-xg-v1": "xg-dc-v1",
    "market-elo-country-v1": "elo-country-v1",
    "market-dc-country-v1": "dixon-coles-country-v1",
}
PER_LEAGUE = {"market-elo-country-v1", "market-dc-country-v1"}
P = ["p_home", "p_draw", "p_away"]


class Combined:
    def __init__(self, version: str) -> None:
        self.version = version
        self.params: dict[str, float | str] = {
            "market": MARKET,
            "model": VARIANTS[version],
            "fit": "per league" if version in PER_LEAGUE else "all leagues",
        }


def inputs(con: duckdb.DuckDBPyConnection, model: str) -> pd.DataFrame:
    """One row per match and horizon that the market and `model` both predicted."""
    return con.execute(
        """
        select match_id, horizon, m.league, season, m.result, mk.prediction_as_of,
            mk.odds_home, mk.odds_draw, mk.odds_away,
            mk.p_home, mk.p_draw, mk.p_away,
            md.p_home as model_home, md.p_draw as model_draw, md.p_away as model_away
        from predictions as mk
        inner join predictions as md using (match_id, horizon)
        inner join wh.int_matches as m using (match_id)
        where mk.model_version = $market and md.model_version = $model
            and m.season >= $development and m.season < $holdout
        order by horizon, season, match_id
        """,
        {
            "market": MARKET,
            "model": model,
            "development": FIRST_DEVELOPMENT_SEASON,
            "holdout": FIRST_HOLDOUT_SEASON,
        },
    ).df()


def features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """log p_market and log p_model, each (n, 3)."""
    return np.log(df[P].to_numpy()), np.log(
        df[["model_home", "model_draw", "model_away"]].to_numpy()
    )


def probs(params: np.ndarray, market: np.ndarray, model: np.ndarray) -> np.ndarray:
    a, b, c_home, c_draw = params
    return np.exp(log_softmax(a * market + b * model + np.array([c_home, c_draw, 0.0]), axis=1))


def fit(market: np.ndarray, model: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Maximum likelihood (a, b, c_home, c_draw); y holds outcome indices 0, 1, 2."""
    rows = np.arange(len(y))
    onehot = np.eye(3)[y]

    def loss(params: np.ndarray) -> tuple[float, np.ndarray]:
        p = probs(params, market, model)
        r = onehot - p
        grad = -np.array([(r * market).sum(), (r * model).sum(), r[:, 0].sum(), r[:, 1].sum()])
        return -np.log(p[rows, y]).sum(), grad

    return minimize(loss, np.array([1.0, 0.0, 0.0, 0.0]), jac=True, method="BFGS").x


def walk_forward(df: pd.DataFrame, per_league: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predictions per match, and the fitted parameters per horizon (and league) and season."""
    out, weights = [], []
    y = df["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    market, model = features(df)
    groups = df["horizon"] + ("|" + df["league"] if per_league else "")
    for group in groups.unique():
        in_group = (groups == group).to_numpy()
        for season in sorted(df.loc[in_group, "season"].unique()):
            train = in_group & (df["season"] < season).to_numpy()
            test = in_group & (df["season"] == season).to_numpy()
            if not train.any():
                continue
            params = fit(market[train], model[train], y[train])
            rows = df[test].copy()
            rows[P] = probs(params, market[test], model[test])
            out.append(rows)
            weights.append((*group.split("|"), season, int(train.sum()), *params))
    columns = ["horizon", *(["league"] if per_league else []), "season", "n_fit"]
    columns += ["market", "model", "c_home", "c_draw"]
    return pd.concat(out), pd.DataFrame(weights, columns=columns)


def predictions(version: str, df: pd.DataFrame) -> list[Prediction]:
    out = []
    for r in df.to_dict("records"):
        key = f"{version}|{r['horizon']}|{r['match_id']}"
        odds = (r["odds_home"], r["odds_draw"], r["odds_away"])
        out.append(
            Prediction(
                hashlib.sha256(key.encode()).hexdigest()[:16],
                r["match_id"],
                r["horizon"],
                r["prediction_as_of"],
                version,
                float(r["p_home"]),
                float(r["p_draw"]),
                float(r["p_away"]),
                *(None if pd.isna(o) else float(o) for o in odds),
            )
        )
    return out


def main() -> None:
    con = connect()
    data = {model: inputs(con, model) for model in VARIANTS.values()}
    con.close()  # save() opens the store for writing
    for version, model in VARIANTS.items():
        df = data[model]
        combined, _ = walk_forward(df, version in PER_LEAGUE)
        rows = predictions(version, combined)
        seasons = sorted(df["season"])
        new = save(rows, [Combined(version)], f"{seasons[0]}..{seasons[-1]}")
        print(f"{version}: {len(rows)} predictions, {new} new")


if __name__ == "__main__":
    main()
