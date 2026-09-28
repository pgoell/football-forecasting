# Experiment spec

Phase 0 of the project. Frozen rules for the first milestone, written before any data is loaded, so success cannot be redefined after the results come in.

Status: frozen 2026-09-28. Changes go in the change log with a date and a reason.

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

## Data

| Need | Source | Cost |
|---|---|---|
| Results, fixtures, `pre` and `close` odds | Football-Data CSVs (`mmz4281/{season}/{E0,D1}.csv`) | free |
| True `T-24h` odds, 2020/21 onward (only if `pre` proves too coarse) | The Odds API, one month of the 100K plan | $59 once |
| Live odds for paper trading | The Odds API, 20K plan | $30/mo |

Football-Data facts that shape the experiment:

- Kickoff time exists only from 2019/20; before that, `available_at` falls back to the match date
- Pinnacle (`PS*`) closing odds: 2012/13 to mid 2025/26; unreliable since 23/07/2025 (210 of 380 E0 and 150 of 306 D1 matches filled in 2025/26), gone in 2026/27
- Closing odds for all bookmakers (`*C*`): from 2019/20
- Betfair Exchange (`BFE*`): from 2024/25
- Terms: private, non-commercial use only

Quotes, archived sources and checks for each fact: `docs/data-sources.md` in the repo.

## Target

`P(Home), P(Draw), P(Away)` per match, summing to 1.

Two horizons:

- `pre`: the Football-Data pre-match snapshot, taken Friday by 17:00 UK time for weekend matches and Tuesday by 13:00 for midweek ones; 20h to 3 days before kickoff, not a fixed `T-24h`
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
4. Sharp market: Pinnacle closing, devigged (the bar to beat); Betfair Exchange closing where Pinnacle is missing (most of 2025/26)

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
- Odds: bet365 (`B365*`), licensed in Germany; no Max odds, no line shopping. Football-Data likely records the international site, not bet365.de, so this stands in for executable odds until paper trading checks them
- Cost: 5.3% of the stake (the law puts the tax on the bookmaker at 5.03% of the gross stake; bet365 says it absorbs it, unverified), so the backtest assumes the worse case
- At most 3 thresholds tried, on validation only; the holdout sees one

## Success criteria

Confidence intervals: 95%, paired bootstrap over matches (block by matchday).

| # | Pass if (holdout) |
|---|---|
| 1 | best model log loss below Elo, CI excludes 0 |
| 2a | best model log loss below sharp market closing (stretch, expected fail) |
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

- [x] Holdout seasons: 2023/24 to 2025/26
- [x] Executable bookmaker: bet365, 5.3% on stake (see Betting rule)
- [x] `pre` timing: use Football-Data first; buy The Odds API snapshots only if timing matters
- [x] Time budget: none

## Change log

- 2026-09-28: first draft
- 2026-09-28: data sources; `pre` timing; Pinnacle dates and Betfair fallback; bet365 as executable odds
- 2026-09-28: frozen; holdout kept at 2023/24 to 2025/26, no time budget
- 2026-09-28: note only, no rule change: the legal tax is 5.3% of the stake net of tax (5.03% gross); the backtest keeps 5.3% as the worse case
- 2026-09-28: pre-registration of a second experiment, written before any data for its leagues is downloaded. For E0 and D1 no model adds information to the market (criterion 2b fails, docs/experiment-log.md). Question: do the same models beat a thinner market? Fixed before any result is seen:
  - Leagues: D2 (2. Bundesliga), E1 (Championship), E2 (League One). No others, and none swapped later.
  - Periods, holdout and scoring as for E0 and D1: warm-up 2000/01 to 2004/05, development 2005/06 to 2018/19, validation 2019/20 to 2022/23; the holdout (2023/24 to 2025/26) is never loaded; `pre` and `close` as above; log loss, Brier and RPS on the matches all models predicted.
  - Models, with the E0 and D1 settings and nothing retuned per league: `naive-v1`, `market-consensus-v1`, Elo with the `elo-v1` settings, Dixon-Coles with the `dixon-coles-v1` settings, and a market-aware blend. One change to Elo and Dixon-Coles: a team that moves between covered leagues of one country (E0, E1, E2; D1, D2) keeps its rating and strengths; the promoted-team prior applies only to teams from below the covered leagues. That changes forecasts for teams that move, so these two are stored as new versions, `elo-country-v1` and `dixon-coles-country-v1`. How they carry is fixed and logged before any development or validation score is seen. No xG (Understat does not cover these leagues), no shots or rest days (no gain in E0 and D1).
  - Blend: the `market_aware.py` model (market and one model, four parameters, refitted before each season on all earlier seasons), fitted per league and horizon, on both Elo and Dixon-Coles. The test uses the one whose base model has the lower development log loss at `pre`, over the three leagues together.
  - Test: criterion 2b per league at `pre` and at `close` on validation: blend log loss minus market log loss, paired over the matches both predicted, bootstrap over matchdays, 10,000 draws. With 3 leagues and 2 horizons, a league and horizon passes only if the 99% interval lies wholly below 0. Seasons where a league has few bookmakers stay in; docs/data-sources.md flags them.
  - Stop rule: if no league passes at either horizon, the betting question (questions 2 to 4) is closed for good: no CLV or profit test, no paper trading, and the project moves to EURO 2028 forecasting. If one passes, that league and horizon get a single holdout run under the same test before anything else.
