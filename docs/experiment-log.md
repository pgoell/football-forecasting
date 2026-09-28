# Experiment log

Every model and betting rule tried, with the date and the data it saw (docs/experiment-spec.md, Rules against fooling ourselves). Newest last. Reproduce a run with `mise run backtest`; stored predictions live in `data/predictions.duckdb` and never change.

## 2026-09-28: Phase 2 engine, first three models

Data seen: warm-up, development and validation seasons (2000/01 to 2022/23). The holdout is never loaded.

Models:

- `naive-v1`: league base rates of H, D and A from all earlier seasons.
- `market-consensus-v1`: median of devigged probabilities across reliable, non-aggregate bookmakers, from the odds of the horizon's own moment. At `close` before 2019/20 only Pinnacle has closing odds (2012/13 onward), so the consensus there is Pinnacle alone.
- `elo-v1`: K 20, home advantage 60, ratings carried across seasons; mapped to H/D/A by an ordered logit on the rating difference, refit on all earlier results at each new season. K and home advantage were fixed by hand, not tuned.

Promoted-team prior: 1400, from `research/elo-promoted-prior/prior.py`, which uses the warm-up seasons only: the mean end-of-season rating of the 24 teams relegated there came out at 1402.

Each table scores the matches all three models predicted. `close` in development covers 2012/13 to 2018/19 only (no closing odds before).

| Period | Horizon | n | Naive | Elo | Market |
|---|---|---|---|---|---|
| development | pre | 9,604 | 1.0636 | 0.9854 | 0.9738 |
| development | close | 4,801 | 1.0639 | 0.9778 | 0.9619 |
| validation | pre | 2,744 | 1.0714 | 0.9933 | 0.9769 |
| validation | close | 2,744 | 1.0714 | 0.9933 | 0.9745 |

Log loss. The market beats Elo at `pre` in all 18 seasons and at `close` in all 11. Leaving out `pre_timing_uncertain` matches moves no log loss by more than 0.002.

Reading: the engine works and shows no sign of leakage (Elo would beat the market if it saw results early). Phase 2 exit criterion met.

## 2026-09-28: first look at the betting rule

Data seen: development seasons (2005/06 to 2018/19), pre-match, using the stored `-v1` predictions. Not the spec's validation run of the rule; a check of whether any model is near break-even. Rerun: `uv run research/first-betting-check/check.py`.

Rule as in the spec: bet the outcome with the highest `EV = p * odds - 1` when EV exceeds a threshold; bet365 pre-match odds, flat 1 unit, 5.3% of the stake as tax. Baseline without a model: back bet365's favourite in every match.

| Rule | Bets | Return per unit |
|---|---|---|
| back the favourite | 9,604 | -9.2% |
| market-consensus-v1, EV > 0 / 5% / 10% | 2,390 / 669 / 260 | -9.9% / -15.3% / -41.3% |
| elo-v1, EV > 0 / 5% / 10% | 7,677 / 5,479 / 3,908 | -11.5% / -13.5% / -13.2% |
| naive-v1, EV > 0 / 5% / 10% | 9,270 / 8,501 / 7,670 | -11.8% / -12.1% / -11.6% |

Reading: every rule loses about what the costs take. bet365's margin (about 5%) and the tax (5.3%) cost about 10% per bet, which is roughly what backing the favourite loses. Elo does worse than that: it is less accurate than the market, so where it disagrees with the odds the odds are usually right, and a higher EV threshold makes it worse, not better. The market model bets only where bet365's price sits above the consensus; the few large gaps (EV > 10%, 260 bets) lose heavily, which points to stale or wrong bet365 prices rather than value. With 2,000 to 9,000 bets the standard error of these returns is 2 to 4 points, so all of them are clearly negative.

No model makes money. A model has to beat the market's log loss, not Elo's, before a betting rule can pay; closing line value (question 3) stays the deciding test.
