# Experiment spec

Phase 0 of the project. Frozen rules for the first milestone, written before any data is loaded, so success cannot be redefined after the results come in.

Status: draft. Freeze once the open decisions below are settled; after that, changes go in the change log with a date and a reason.

## Questions

Four questions, in order. Each one only matters if the one before it holds.

1. **Forecast:** do our models predict 1X2 better than Elo?
2. **Market:** does our model beat the devigged market, or at least add signal to it?
3. **CLV:** do the bets our model picks beat the closing line on average?
4. **Profit:** does a fixed betting rule make money after margin and German betting tax?

Expected answer: yes to 1, no or barely to 2, unknown for 3 and 4. A clean "no" to 3 is a valid result.

## Scope

| | In | Out |
|---|---|---|
| Leagues | Premier League (E0), Bundesliga (D1) | all others, cups, internationals |
| Market | 1X2 | over/under, handicap, exact score |
| Data | results, fixtures, pre-match and closing odds | xG, lineups, injuries (Phase 4) |
| Models | naive, Elo, Poisson, Dixon-Coles, market consensus | trees, ensembles (Phase 5) |
| Money | none | real bets (Phase 7 at the earliest) |

Source: Football-Data (football-data.co.uk). Odds from ~2000/01; closing odds only from 2019/20.

## Target

`P(Home), P(Draw), P(Away)` per match, summing to 1.

Two horizons:

- `pre`: the Football-Data pre-match odds snapshot (unsure of the exact capture time, check before freezing; not a true `T-24h`)
- `close`: closing odds

A prediction may use only data with `available_at` before the horizon.

## Data periods

| Period | Seasons | Use |
|---|---|---|
| Warm-up | 2000/01 to 2004/05 | fit Elo and team ratings only, no scoring |
| Development | 2005/06 to 2018/19 | walk-forward, free to iterate |
| Validation | 2019/20 to 2022/23 | pick model and betting rule, closing odds exist |
| Holdout | 2023/24 to 2025/26 | locked, run exactly once |
| Prospective | 2026/27 onward | paper predictions logged before kick-off (Phase 7) |

Holdout size: ~2,060 matches (3 seasons of 380 EPL + 306 BL).

Walk-forward: refit or update before each matchday, never with a later match.

## Benchmarks

1. Naive: league base rates of H/D/A from prior seasons
2. Elo: home advantage included, ratings carried across seasons
3. Market: devigged by normalization, median across bookmakers
4. Sharp market: Pinnacle closing, devigged (the bar to beat)

## Metrics

| Role | Metric |
|---|---|
| Primary forecast | log loss |
| Secondary forecast | Brier, RPS, calibration curve |
| Primary market | mean CLV of bets taken |
| Primary profit | net ROI, flat stake |
| Reported | bet count, max drawdown, P&L curve |

CLV per bet = `odds_taken / close_odds_devigged - 1`.

## Betting rule

- Bet when `EV = p_model * odds - 1` exceeds a threshold
- Flat 1-unit stake, at most one outcome per match
- Odds: one bookmaker that takes German customers (not Max odds, no line shopping)
- Cost: 5.3% German betting tax on stake, unless the chosen bookmaker already prices it in
- At most 3 thresholds tried, on validation only; the holdout sees one

## Success criteria

Confidence intervals: 95%, paired bootstrap over matches (block by matchday).

| # | Pass if (holdout) |
|---|---|
| 1 | best model log loss below Elo, CI excludes 0 |
| 2a | best model log loss below Pinnacle closing (stretch, expected fail) |
| 2b | market-aware model log loss below market alone, CI excludes 0 |
| 3 | mean CLV > 0, CI excludes 0, at least 300 bets |
| 4 | net ROI > 0 after tax |

Criterion 4 alone proves little. At average odds ~2.5, flat-stake ROI has a standard error of ~9% at 200 bets and ~4% at 1,000. So criterion 3 decides whether the project goes to paper trading, not 4.

## Decisions that follow

- Fail 1: fix the models before anything else
- Pass 1, fail 3: forecasting project only; no paper trading, no money
- Pass 3: start prospective paper trading (Phase 7), target 500+ logged bets before any real money
- Pass 3 and 4 on paper: tiny real-money test, a stake cap agreed in advance

## Rules against fooling ourselves

- Every model and betting rule tried goes in an experiment log, with the date and the data period it saw
- Nothing is tuned on the holdout; a second holdout run counts as a new experiment and needs new seasons
- Predictions are stored immutable: `prediction_id, match_id, prediction_as_of, model_version, p_home, p_draw, p_away, odds_*`
- Promoted teams get a fixed prior rating, set before development starts

## Open decisions

- [ ] Holdout seasons: 2023/24 to 2025/26 as above, or shorter validation for a larger holdout?
- [ ] Which bookmaker counts as executable (Bet365? others in the Football-Data files?) and how its tax shows up in the odds
- [ ] Football-Data `pre` snapshot timing: good enough, or buy historical snapshots (The Odds API, from June 2020) for a true `T-24h`?
- [ ] Time budget for Phases 1 to 3

## Change log

- 2026-09-28: first draft
