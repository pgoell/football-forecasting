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

## 2026-09-28: Phase 3, goal models

Data seen: warm-up, development and validation seasons (2000/01 to 2022/23). The holdout is never loaded. Settings were fixed before any development or validation score was seen, and nothing was tuned.

Models:

- `poisson-v1`: home and away goals independent Poisson, `log(rate) = mean + attack + defence (+ home)`, fitted per league by penalized maximum likelihood on the current and two previous seasons, all matches weighted the same. Refit before a prediction whenever the league has new results, so at most once per prediction time. H/D/A from the score grid up to 10 goals a side.
- `dixon-coles-v1`: the same plus the Dixon-Coles factor on 0-0, 1-0, 0-1 and 1-1 (rho, fitted, bounded to ±0.3) and weight `exp(-xi * age in days)` with xi = 0.0065 per half week, the value Dixon and Coles (1997) report; half-life about a year.

Settings and where they come from:

| Setting | Value | Source |
|---|---|---|
| window | 3 seasons | by hand |
| xi | 0.0065 / 3.5 per day | by hand, from the paper |
| promoted prior | attack −0.32, defence +0.25 | warm-up seasons, `research/goal-model-prior/prior.py` |
| penalty sd | 0.24 | warm-up seasons, same script |

The penalty pulls each team's attack and defence toward 0, or toward the promoted prior for a team not in the league the season before, with weight `1 / (2 sd^2)`. The script fits each warm-up league season on its own; the prior is the mean strength of the 24 teams relegated there (as for `elo-v1`), sd the spread of all team strengths. A team with no match in the window sits exactly at its target.

Log loss, each row on the matches all five models predicted (`mise run backtest`):

| Period | Horizon | n | Naive | Elo | Poisson | Dixon-Coles | Market |
|---|---|---|---|---|---|---|---|
| development | pre | 9,604 | 1.0636 | 0.9854 | 0.9879 | 0.9874 | 0.9738 |
| development | close | 4,801 | 1.0639 | 0.9778 | 0.9800 | 0.9801 | 0.9619 |
| validation | pre | 2,744 | 1.0714 | 0.9933 | 0.9948 | 0.9910 | 0.9769 |
| validation | close | 2,744 | 1.0714 | 0.9933 | 0.9948 | 0.9911 | 0.9745 |

Paired differences in log loss, 95% bootstrap interval over matchdays (`uv run research/goal-models-check/check.py`):

| Period | Horizon | Poisson − Elo | DC − Elo | DC − Poisson | DC − Market |
|---|---|---|---|---|---|
| development | pre | +0.0025 (−0.0002, +0.0056) | +0.0020 (−0.0004, +0.0048) | −0.0005 (−0.0020, +0.0011) | +0.0136 (+0.0107, +0.0169) |
| development | close | +0.0022 (−0.0016, +0.0064) | +0.0022 (−0.0011, +0.0058) | +0.0000 (−0.0020, +0.0020) | +0.0182 (+0.0130, +0.0231) |
| validation | pre | +0.0015 (−0.0048, +0.0080) | −0.0023 (−0.0074, +0.0027) | −0.0038 (−0.0074, −0.0001) | +0.0141 (+0.0080, +0.0199) |
| validation | close | +0.0015 (−0.0048, +0.0076) | −0.0022 (−0.0076, +0.0030) | −0.0037 (−0.0070, −0.0005) | +0.0166 (+0.0097, +0.0236) |

Without `pre_timing_uncertain` matches (pre only; close is unchanged): development pre n 9,056, Poisson − Elo +0.0020 (−0.0007, +0.0049), DC − Elo +0.0016 (−0.0010, +0.0043), DC − Market +0.0136; validation pre n 2,600, Poisson − Elo +0.0023, DC − Elo −0.0017 (−0.0071, +0.0039), DC − Market +0.0136. No conclusion changes.

**Do goal models beat Elo?** No. In development both are about 0.002 worse than Elo, the interval touching 0; in validation Dixon-Coles is 0.002 better, the interval wide on both sides of 0. By season, Dixon-Coles beats Elo in 9 of 18 pre-match seasons. Call it a tie. Dixon-Coles beats plain Poisson in validation (0.004, interval just clear of 0) but not in development.

**How close to the market?** No closer than Elo. Dixon-Coles trails the market by 0.014 at `pre` and 0.017 to 0.018 at `close`, every interval clear of 0; Elo trails by 0.012 to 0.019. The gap is widest at `close`, likely because the market has the team news by then.

**Where is calibration poor?** From the calibration bins, development and validation, pre, bins with at least 100 forecasts:

- Draws. Poisson forecasts too few: 23.5% against 24.6% observed, and 24.8% against 26.2% in its main bin. Dixon-Coles gets the overall rate right (25.2% against 24.6%) but overshoots at both ends: 17.0% forecast against 13.8% observed in lopsided matches, 31.2% against 28.5% in the tightest ones. The market is close in every bin.
- Big favourites. Both goal models are too cautious: Dixon-Coles home wins at 64.6% happen 69.5% of the time, at 83.2% 87.5%; away wins at 64.2% happen 72.4%. The likely cause is the penalty and the three-season window pulling strong teams toward the average.
- Elo errs the other way on home favourites (54.7% forecast, 50.7% observed) and underrates away teams overall (28.5% against 29.8%).

Reading: results-only Elo and goal-based models carry about the same information; neither is near the market. Phase 3 exit criterion answered. Candidates for a `-v2`, to tune on development seasons only: a weaker penalty or shorter window for the favourite bias, and xi chosen on development.

## 2026-09-28: question 2b, market-aware models

Data seen: development and validation seasons (2005/06 to 2022/23), through the stored predictions of `market-consensus-v1`, `elo-v1` and `dixon-coles-v1`. The holdout is never loaded. No base model is refit; nothing was tuned.

Models (`src/football_forecasting/market_aware.py`):

- `market-elo-v1`, `market-dc-v1`: a multinomial logit on the stored forecasts at the same horizon, `P(k) ∝ exp(a * log p_market[k] + b * log p_model[k] + c[k])`, `c[A] = 0`, with `elo-v1` or `dixon-coles-v1` as the model. `b` is the weight our model gets; `a = 1, b = 0, c = 0` returns the market. No other features.
- Fitted by plain maximum likelihood, no penalty, per horizon, both leagues together, before each season on all earlier seasons from 2005/06. Four parameters on at least 686 matches: the fit is well defined without a penalty.
- The first season of each horizon has nothing to fit on, so forecasts start in 2006/07 at `pre` and 2013/14 at `close` (market closing odds start in 2012/13). `pre_timing_uncertain` matches stay in every fit; they are left out only in the scoring below.

Log loss minus market, paired over the matches all three predicted, 95% bootstrap interval over matchdays (`uv run research/market-aware-check/check.py`; same method as `research/goal-models-check/`, now `report.bootstrap`):

| Period | Horizon | n | Market | market-elo − Market | market-dc − Market |
|---|---|---|---|---|---|
| development | pre | 8,918 | 0.9744 | +0.0006 (−0.0008, +0.0020) | +0.0005 (−0.0007, +0.0018) |
| development | close | 4,115 | 0.9602 | +0.0024 (+0.0007, +0.0042) | +0.0024 (+0.0009, +0.0041) |
| validation | pre | 2,744 | 0.9769 | +0.0008 (−0.0003, +0.0019) | +0.0009 (−0.0001, +0.0019) |
| validation | close | 2,744 | 0.9745 | +0.0002 (−0.0003, +0.0007) | +0.0003 (−0.0002, +0.0008) |

Without `pre_timing_uncertain` matches (pre only; close is unchanged): development pre n 8,407, +0.0004 (−0.0010, +0.0017) and +0.0003 (−0.0010, +0.0016); validation pre n 2,600, +0.0009 (−0.0003, +0.0021) and +0.0010 (−0.0001, +0.0021). No conclusion changes.

**Criterion 2b: fails on validation.** Neither variant beats the market; both point estimates are slightly worse and every interval holds 0. In development at `close` both are worse with the interval clear of 0: the loss comes from 2013/14 to 2016/17 (+0.007, +0.004, +0.001, +0.002), when the fit had only 686 to 2,744 Pinnacle closing matches and gave our model weight 0.1 to 0.4. From 2017/18 the per-season gap stays within ±0.001.

Fitted weights, selected seasons (all seasons: the check script):

| Variant | Horizon | Season fitted for | n fit | a (market) | b (model) | c_home | c_draw |
|---|---|---|---|---|---|---|---|
| market-elo | pre | 2006/07 | 686 | 1.816 | −0.428 | −0.015 | +0.033 |
| market-elo | pre | 2012/13 | 4,802 | 1.126 | −0.053 | +0.054 | +0.035 |
| market-elo | pre | 2019/20 | 9,604 | 1.127 | −0.068 | +0.053 | +0.027 |
| market-elo | pre | 2022/23 | 11,662 | 1.112 | −0.079 | +0.042 | +0.012 |
| market-elo | close | 2013/14 | 686 | 0.889 | +0.343 | −0.206 | +0.110 |
| market-elo | close | 2019/20 | 4,801 | 1.020 | −0.013 | +0.046 | +0.015 |
| market-elo | close | 2022/23 | 6,859 | 1.034 | −0.046 | +0.026 | −0.007 |
| market-dc | pre | 2006/07 | 686 | 1.491 | −0.185 | −0.017 | +0.047 |
| market-dc | pre | 2012/13 | 4,802 | 1.056 | +0.020 | +0.045 | +0.035 |
| market-dc | pre | 2019/20 | 9,604 | 1.070 | −0.008 | +0.043 | +0.026 |
| market-dc | pre | 2022/23 | 11,662 | 1.026 | +0.018 | +0.027 | +0.010 |
| market-dc | close | 2013/14 | 686 | 0.870 | +0.397 | −0.183 | +0.114 |
| market-dc | close | 2019/20 | 4,801 | 1.009 | +0.000 | +0.043 | +0.015 |
| market-dc | close | 2022/23 | 6,859 | 0.983 | +0.017 | +0.014 | −0.009 |

**How much weight does our model get?** Almost none, once the fit has a few thousand matches. `b` for Dixon-Coles stays between −0.01 and +0.08 at `pre` from 2012/13 and between 0.00 and +0.06 at `close` from 2017/18; for Elo it drifts from 0.00 to −0.08 at `pre` from 2013/14, so the fit moves slightly away from Elo where Elo disagrees with the market. **Is it stable?** Only after a few seasons of data. The first fits swing widely (`b` from −0.45 to +0.40, `a` up to 1.8, `a` and `b` trading off because the two inputs are highly correlated), then settle. What the fit does keep is a small recalibration of the market itself: at `pre` from 2012/13, `a` is 1.02 to 1.13 (the pre-match market is slightly too cautious) and `c_home` +0.01 to +0.06 (it slightly underrates home wins). Both variants gain and lose in the same seasons: the gains and losses come from this recalibration, not from our models. It cost 0.002 at `pre` in each of 2019/20 and 2020/21, seasons played partly or wholly without crowds, where a push toward home wins likely hurt.

**Does disagreement carry information?** No. Matches binned by `p_model − p_market` for the home win, observed home-win rate against the market's forecast (development and validation pooled per row, `pre`; points):

| Gap, points | Elo: n | Elo: observed − market | DC: n | DC: observed − market |
|---|---|---|---|---|
| < −10 | 239 | +0.024 | 722 | −0.008 |
| −10 to −6 | 666 | +0.005 | 1,321 | +0.014 |
| −6 to −3 | 1,153 | +0.023 | 1,633 | +0.015 |
| −3 to −1 | 1,276 | +0.014 | 1,294 | +0.015 |
| −1 to +1 | 1,552 | +0.011 | 1,451 | +0.008 |
| +1 to +3 | 1,787 | +0.012 | 1,554 | +0.009 |
| +3 to +6 | 2,418 | +0.009 | 1,966 | +0.013 |
| +6 to +10 | 2,082 | +0.015 | 1,655 | +0.018 |
| > +10 | 1,175 | −0.011 | 752 | −0.005 |

If our model knew something, `observed − market` would rise from the top of the table to the bottom. It stays flat, at about +0.01 in every bin: the market's general underrating of home wins in these seasons, the same as `c_home`, whatever the model says. The biggest disagreements (over 10 points) come out slightly below the market, not above. The slope of `observed − market` on the gap, per period and horizon, is between −0.11 and −0.01 for Elo and between −0.01 and +0.07 for Dixon-Coles (1 would mean the model is right, 0 that it adds nothing). Every bin lies within its own 95% margin of 0 (±0.02 to ±0.13; full tables by period and horizon, with and without `pre_timing_uncertain`, in the check script's output). `close` shows the same picture.

Reading: our results-only models add nothing measurable to the market at either horizon. What little a blend gains comes from recalibrating the market, and even that does not survive out of sample. Criterion 2b fails on validation, as the spec expected; there is no holdout run to make. Question 3 (CLV) is still worth running, since it tests the betting rule directly, but with no forecasting edge a positive CLV would more likely point to stale bet365 prices than to our models.
