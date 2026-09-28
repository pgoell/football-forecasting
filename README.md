# football-forecasting

Predict football matches with statistical models (Elo, Poisson, Dixon-Coles, later gradient boosting), then test whether the forecasts beat the betting market after costs.

First milestone: Premier League and Bundesliga, 1X2 (home win, draw, away win) only, strict walk-forward backtest against Elo and the devigged market. Second experiment: the same question in thinner markets, 2. Bundesliga, Championship and League One (pre-registered in the spec's change log).

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

## Backtest

```sh
mise run backtest  # predict, store in data/predictions.duckdb, print scores
```

The engine (`src/football_forecasting/backtest.py`) walks matches in time order and hands a model only results and odds known before the prediction time; its docstring gives the timing rules. Stored predictions never change: a model that gives new numbers needs a new version. Runs and results: [docs/experiment-log.md](docs/experiment-log.md).

Each backtest run gets a row per model in the `runs` table (git commit, uncommitted changes, parameters, seasons seen); each prediction keeps the run that first stored it.

## Dashboard

```sh
mise run dashboard         # local, http://127.0.0.1:8501
mise run dashboard:deploy  # container on the VPS, https://football.pascalkraus.com
```

Scores, log loss by season, the gap to a reference model, calibration and runs, read from the stores read-only. A Glossary page explains the terms and each model (`src/football_forecasting/glossary.md`). Holdout seasons never reach it. The public route sits behind the GitHub login in `server-infra` (Caddy route and Cloudflare DNS record there).

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
