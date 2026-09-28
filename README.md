# football-forecasting

Predict football matches with statistical models (Elo, Poisson, Dixon-Coles, later gradient boosting), then test whether the forecasts beat the betting market after costs.

First milestone: Premier League and Bundesliga, 1X2 (home win, draw, away win) only, strict walk-forward backtest against Elo and the devigged market.

The rules of the experiment live in [docs/experiment-spec.md](docs/experiment-spec.md). Read them before changing a model or a metric.

## Setup

Needs [mise](https://mise.jdx.dev).

```sh
mise install      # python, uv, lefthook
mise run install  # git hooks + dependencies
mise run test
mise run lint     # ruff + ty
```

## Data

```sh
mise run data:download  # Football-Data CSVs into data/raw/
mise run dbt:build      # dbt models and tests into data/warehouse.duckdb
```

Where each fact about the data comes from, and how to check it: [docs/data-sources.md](docs/data-sources.md).

## Phases

0. Define the experiment
1. Data warehouse (Parquet, DuckDB, dbt; every row carries `available_at`)
2. Backtesting engine
3. Statistical baseline
4. Richer features (xG, rest, players)
5. ML (LightGBM, XGBoost, calibration, ensembles)
6. Market modeling
7. Paper betting
8. Production
9. EURO 2028
