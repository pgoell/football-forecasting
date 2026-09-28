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

## 2026-09-28: Phase 4, shots and rest days

Data seen: warm-up, development and validation seasons (2000/01 to 2022/23). The holdout is never loaded. The one setting, the shots weight, was chosen on development seasons only, before any validation score was seen.

New data (Football-Data CSVs, `docs/data-sources.md`): shots and shots on target per team and match, and rest days (days since each team's previous match, and its matches in the 14 days before) from fixture dates. The files hold league matches only, so rest days miss cup and European games.

### Rest days: no signal, no adjustment

Development seasons, `pre`, stored forecasts of the market and Dixon-Coles (`uv run research/rest-days-check/check.py`). Rest difference = home minus away rest days, each capped at 8.

| Model | Slope of (observed − forecast) home win on rest difference, per day | on difference in matches in 14 days |
|---|---|---|
| Market | −0.0006 ± 0.0096 | −0.0008 ± 0.0204 |
| Dixon-Coles | −0.0006 ± 0.0097 | −0.0009 ± 0.0206 |

Both slopes are 0 for both models, and no rest-difference bin lies outside its 95% margin. In 60% of matches both teams had the same rest, because the files carry no midweek cup or European games. With nothing to find, no model gets a rest adjustment; the columns stay in `int_matches`.

### shots-dc-v1

`shots-dc-v1`: `dixon-coles-v1` with the rates fitted to `(1 − w) × goals + w × c × shots on target` instead of goals, where `c` is the league's goals per shot on target in the fit window (0.24 in E0, 0.29 in D1 over development). Everything else is `dixon-coles-v1` unchanged, and the low-score factor still uses the score. D1 2002/03 to 2005/06 have no shots on target; those matches count their goals.

Choosing w on development only (`OMP_NUM_THREADS=1 uv run research/shots-weight/choose.py`: the engine walks warm-up and development matches, validation is not passed in, nothing is stored):

| w | log loss pre | log loss close |
|---|---|---|
| 0 (= dixon-coles-v1) | 0.9874 | 0.9874 |
| 0.25 | 0.9875 | 0.9874 |
| 0.5 | 0.9889 | 0.9888 |
| 0.75 | 0.9917 | 0.9916 |
| 1 (shots on target only) | 0.9959 | 0.9959 |

(`close` here scores every development match, not only those with closing odds.) The more weight on shots, the worse. Stored: w = 0.25, the most weight that costs nothing on development, so the model differs from Dixon-Coles at all. A likely reason, not tested: one conversion rate per league treats every shot on target as worth the same, but strong teams create better chances and convert more of them, so a shots-based strength pulls strong teams toward the average, the bias Dixon-Coles already shows.

Paired differences in log loss, 95% bootstrap interval over matchdays, on the matches naive, Elo, Dixon-Coles, shots-dc and the market all predicted (`uv run research/phase4-check/check.py shots-dc-v1`):

| Period | Horizon | n | shots-dc | − Naive | − Elo | − Dixon-Coles | − Market |
|---|---|---|---|---|---|---|---|
| development | pre | 9,604 | 0.9875 | −0.0761 (−0.0822, −0.0698) | +0.0021 (−0.0008, +0.0047) | +0.0000 (−0.0007, +0.0007) | +0.0136 (+0.0106, +0.0167) |
| development | close | 4,801 | 0.9803 | −0.0836 (−0.0933, −0.0740) | +0.0025 (−0.0016, +0.0065) | +0.0002 (−0.0007, +0.0012) | +0.0184 (+0.0137, +0.0236) |
| validation | pre | 2,744 | 0.9906 | −0.0808 (−0.0930, −0.0675) | −0.0027 (−0.0077, +0.0026) | −0.0004 (−0.0018, +0.0008) | +0.0137 (+0.0083, +0.0193) |
| validation | close | 2,744 | 0.9907 | −0.0807 (−0.0938, −0.0680) | −0.0026 (−0.0081, +0.0029) | −0.0004 (−0.0016, +0.0009) | +0.0162 (+0.0094, +0.0233) |

Without `pre_timing_uncertain` matches (pre only): development n 9,056, − Dixon-Coles +0.0001 (−0.0006, +0.0009), − Market +0.0137; validation n 2,600, − Dixon-Coles −0.0004 (−0.0017, +0.0009), − Market +0.0132. No conclusion changes.

### market-shots-v1: does shots-dc add to the market?

`market-shots-v1`: the market-aware blend of question 2b (`market_aware.py`, unchanged) with `shots-dc-v1` as the model. Log loss minus market, paired, same method:

| Period | Horizon | n | Market | market-shots − Market | for comparison: market-dc − Market |
|---|---|---|---|---|---|
| development | pre | 8,918 | 0.9744 | +0.0005 (−0.0007, +0.0018) | +0.0005 (−0.0007, +0.0018) |
| development | close | 4,115 | 0.9602 | +0.0025 (+0.0008, +0.0043) | +0.0024 (+0.0009, +0.0041) |
| validation | pre | 2,744 | 0.9769 | +0.0009 (−0.0001, +0.0020) | +0.0009 (−0.0001, +0.0019) |
| validation | close | 2,744 | 0.9745 | +0.0003 (−0.0002, +0.0008) | +0.0003 (−0.0002, +0.0008) |

Fitted weight `b` on shots-dc: +0.02 to +0.15 at `pre` from 2012/13, −0.02 to +0.07 at `close` from 2017/18; slightly above what Dixon-Coles got, but the blend scores no better. Slope of (observed − market) on (model − market) for the home win: −0.000 ± 0.146 (development pre), +0.035 ± 0.245 (validation pre), +0.058 ± 0.171 and −0.003 ± 0.228 at `close`; 0 means no information.

### Answers

- **Which feature helps?** Neither. Rest days show no effect on results the market or Dixon-Coles missed. Shots on target make Dixon-Coles worse the more weight they get; at w = 0.25 the model ties Dixon-Coles (every interval within ±0.002 and holding 0).
- **Does shots-dc beat the base models?** It beats naive by 0.08, ties Elo and Dixon-Coles, and trails the market by 0.014 at `pre` and 0.016 to 0.018 at `close`, the same gap as Dixon-Coles.
- **Does it add information to the market?** No, at either horizon. `market-shots-v1` scores the same as `market-dc-v1`, slightly worse than the market, every validation interval holding 0; the disagreement slope is 0.

Reading: Football-Data shot counts carry no information that goals and the market do not already carry. xG is the next candidate source.

## 2026-09-28: Phase 4, xG

Data seen: warm-up, development and validation seasons (2000/01 to 2022/23); xG from 2014/15. The holdout is never loaded. The one setting, the xG weight, was chosen on development seasons 2014/15 to 2018/19 only, before any validation score was seen.

Source: Understat, downloaded against its robots.txt by the owner's decision (`docs/data-sources.md`). Every Football-Data match from 2014/15 matches exactly one Understat match (dbt tests).

### xg-dc-v1

`xg-dc-v1`: `dixon-coles-v1` with the rates fitted to `(1 − w) × goals + w × xG`. Matches in the window without xG (before 2014/15) count their goals. Forecasts from 2014/15 only.

Choosing w on development only (`OMP_NUM_THREADS=1 uv run research/xg-weight/choose.py`; validation not passed in, nothing stored), 2014/15 to 2018/19, 3,430 matches:

| w | log loss pre | log loss close |
|---|---|---|
| 0 (= dixon-coles-v1) | 0.9845 | 0.9844 |
| 0.25 | 0.9841 | 0.9840 |
| 0.5 | 0.9844 | 0.9843 |
| 0.75 | 0.9853 | 0.9852 |
| 1 (xG only) | 0.9869 | 0.9867 |

Stored: w = 0.25. Unlike shots on target, a little xG helps, but xG alone is worse than goals alone.

Paired differences in log loss, 95% bootstrap interval over matchdays, on the matches naive, Elo, Dixon-Coles, xg-dc and the market all predicted, so 2014/15 onward (`uv run research/phase4-check/check.py xg-dc-v1`):

| Period | Horizon | n | xg-dc | − Naive | − Elo | − Dixon-Coles | − Market |
|---|---|---|---|---|---|---|---|
| development | pre | 3,430 | 0.9841 | −0.0787 (−0.0894, −0.0684) | +0.0022 (−0.0021, +0.0063) | −0.0004 (−0.0011, +0.0004) | +0.0177 (+0.0120, +0.0231) |
| development | close | 3,429 | 0.9843 | −0.0786 (−0.0910, −0.0672) | +0.0021 (−0.0020, +0.0066) | −0.0004 (−0.0013, +0.0004) | +0.0180 (+0.0119, +0.0242) |
| validation | pre | 2,744 | 0.9892 | −0.0822 (−0.0948, −0.0687) | −0.0041 (−0.0090, +0.0010) | −0.0019 (−0.0031, −0.0007) | +0.0122 (+0.0070, +0.0176) |
| validation | close | 2,744 | 0.9893 | −0.0822 (−0.0955, −0.0692) | −0.0040 (−0.0093, +0.0014) | −0.0019 (−0.0029, −0.0007) | +0.0147 (+0.0082, +0.0218) |

Without `pre_timing_uncertain` matches (pre only): development n 3,219, − Dixon-Coles −0.0004 (−0.0013, +0.0004), − Market +0.0170; validation n 2,600, − Dixon-Coles −0.0017 (−0.0029, −0.0006), − Market +0.0118. No conclusion changes.

### market-xg-v1: does xg-dc add to the market?

`market-xg-v1`: the question 2b blend with `xg-dc-v1`. Its first fit needs a season of xg-dc forecasts, so it starts in 2015/16. Log loss minus market, paired; `market-dc-v1` on the same matches for comparison:

| Period | Horizon | n | market-xg − Market | market-dc − Market |
|---|---|---|---|---|
| development | pre | 2,744 | +0.0008 (−0.0008, +0.0026) | +0.0001 (−0.0013, +0.0014) |
| development | close | 2,743 | +0.0014 (−0.0008, +0.0036) | +0.0008 (+0.0001, +0.0015) |
| validation | pre | 2,744 | +0.0008 (−0.0003, +0.0019) | +0.0009 (−0.0001, +0.0019) |
| validation | close | 2,744 | +0.0005 (−0.0005, +0.0016) | +0.0003 (−0.0002, +0.0008) |

Without `pre_timing_uncertain` (pre): development +0.0007 (−0.0009, +0.0024), validation +0.0010 (−0.0001, +0.0020).

Fitted weight `b` on xg-dc: +0.11 and +0.03 in the first two `pre` fits, then negative, −0.21 to −0.04, from 2017/18; at `close` from −0.14 to +0.01 from 2017/18. The fit leans slightly away from xg-dc where it disagrees with the market. Slope of (observed − market) on (model − market), home win: −0.022 ± 0.226 (development pre), +0.046 ± 0.253 (validation pre), +0.078 ± 0.205 and +0.005 ± 0.235 at `close`.

## Phase 4 answers

- **Which feature helps?** xG, a little. `xg-dc-v1` beats Dixon-Coles by 0.0019 on validation at both horizons, the interval clear of 0; on development by 0.0004, the interval holding 0. Shots on target and rest days do not help (previous entry).
- **By how much, against the benchmarks (2014/15 onward)?** xg-dc beats naive by 0.08. Against Elo it is 0.002 worse on development and 0.004 better on validation, both intervals holding 0: still a tie. It trails the market by 0.018 on development and 0.012 to 0.015 on validation, every interval clear of 0. It is the best of our models on validation, and the gap to the market is its narrowest yet, but the gap is still about six times what xG gained.
- **Does any new model add information to the market?** No, at either horizon. `market-shots-v1` and `market-xg-v1` score the same as the market or slightly worse, every validation interval holding 0, and the disagreement slopes are 0. The market already prices what shots and xG say.

Reading: features built from what happened in past matches (goals, shots, xG, schedule) have reached the market's level of information and no further. What the market has and we lack is likely news before the match: line-ups, injuries, suspensions and transfers. Question 2b still fails; question 3 (CLV) remains open.

## 2026-09-28: thin markets, D2, E1 and E2

The question and the test were pre-registered in `docs/experiment-spec.md` (change log, 2026-09-28) before any data for these leagues was downloaded. Data seen: warm-up, development and validation seasons (2000/01 to 2022/23) of D2, E1 and E2, besides E0 and D1. The holdout is never loaded. Nothing was tuned.

### How the models carry teams across leagues

Fixed and written here before any development or validation score of these leagues was seen. The only look at data was the warm-up check below.

- `elo-country-v1`: `elo-v1` (K 20, home advantage 60, one ordered logit on all matches it sees, refit each season) with ratings keyed by country, not league, so a team keeps its rating when it goes up or down. A team in none of the country's covered leagues the season before (from the Regionalliga or 3. Liga into D2, from League Two or the National League into E2) starts at the mean rating of the league it enters, over that league's teams of the season before, minus 100: the `elo-v1` gap between its promoted rating (1400) and the league average (1500). In 2000/01 every team starts at 1500 less 100 per tier below the top (E1 and D2 at 1400, E2 at 1300); the warm-up seasons then move the levels.
- `dixon-coles-country-v1`: `dixon-coles-v1` (window of three seasons, xi, promoted prior and penalty sd unchanged) fitted on all covered leagues of a country together, so a team that moved has one attack and one defence fitted on its matches in both leagues. One mean for the country; home advantage and rho per league, as `dixon-coles-v1` fits them per league. The penalty pulls each team toward its league's level instead of toward 0: a free attack and defence level per league, 0 in the top league, fixed by the teams that moved. A team from below the covered leagues gets the promoted prior (attack −0.32, defence +0.25) on top of its league's level. A team's league is the one of its latest season in the window.
- The engine runs both on all five leagues, so they also store forecasts for E0 and D1; those are not part of this test. The first experiment's models (`elo-v1`, `poisson-v1`, `dixon-coles-v1`, `shots-dc-v1`, `xg-dc-v1`) still run on E0 and D1 only, and their stored forecasts do not change: `elo-v1`'s single ordered logit would move with more leagues. `naive-v1` and `market-consensus-v1` work per league and run on all five.
- Blends `market-elo-country-v1` and `market-dc-country-v1`: `market_aware.py` unchanged, fitted per league and horizon.

Warm-up check (`uv run research/country-levels/levels.py`, warm-up seasons only): where the league levels stand after each season.

| After | E0 | E1 | E2 | D1 | D2 |
|---|---|---|---|---|---|
| Elo mean, 2000/01 | 1500 | 1400 | 1300 | 1500 | 1400 |
| Elo mean, 2004/05 | 1545 | 1399 | 1250 | 1529 | 1351 |
| DC attack / defence level, 2001/02 | 0 / 0 | −0.40 / +0.40 | −0.65 / +0.65 | 0 / 0 | −0.33 / +0.39 |
| DC attack / defence level, 2004/05 | 0 / 0 | −0.34 / +0.37 | −0.51 / +0.65 | 0 / 0 | −0.32 / +0.29 |

The Dixon-Coles levels settle within a season, at about the size of the promoted prior per step down. The Elo gaps are still widening at the end of the warm-up (from 100 to about 150 per step), since only the few teams that move each season carry rating between leagues; within a league only rating differences matter, so this touches promoted and relegated teams alone.

### Log loss per league

On the matches all six models predicted, so the blends' first season (2005/06 at `pre`, 2012/13 at `close`) drops out (`uv run research/thin-markets-check/check.py`):

| League | Period | Horizon | n | Naive | Elo-country | DC-country | Market | market-elo-country | market-dc-country |
|---|---|---|---|---|---|---|---|---|---|
| D2 | development | pre | 3,978 | 1.0748 | 1.0550 | 1.0565 | 1.0417 | 1.0446 | 1.0441 |
| D2 | development | close | 1,836 | 1.0860 | 1.0800 | 1.0796 | 1.0613 | 1.0648 | 1.0644 |
| D2 | validation | pre | 1,224 | 1.0793 | 1.0535 | 1.0545 | 1.0458 | 1.0458 | 1.0455 |
| D2 | validation | close | 1,224 | 1.0793 | 1.0534 | 1.0544 | 1.0438 | 1.0451 | 1.0454 |
| E1 | development | pre | 7,176 | 1.0754 | 1.0537 | 1.0542 | 1.0427 | 1.0440 | 1.0443 |
| E1 | development | close | 3,312 | 1.0789 | 1.0485 | 1.0507 | 1.0278 | 1.0318 | 1.0313 |
| E1 | validation | pre | 2,208 | 1.0814 | 1.0579 | 1.0569 | 1.0461 | 1.0476 | 1.0474 |
| E1 | validation | close | 2,208 | 1.0814 | 1.0578 | 1.0569 | 1.0453 | 1.0465 | 1.0467 |
| E2 | development | pre | 7,176 | 1.0761 | 1.0568 | 1.0577 | 1.0408 | 1.0428 | 1.0430 |
| E2 | development | close | 3,312 | 1.0788 | 1.0602 | 1.0622 | 1.0382 | 1.0397 | 1.0399 |
| E2 | validation | pre | 2,055 | 1.0746 | 1.0373 | 1.0377 | 1.0146 | 1.0129 | 1.0130 |
| E2 | validation | close | 2,056 | 1.0745 | 1.0372 | 1.0376 | 1.0104 | 1.0097 | 1.0101 |

These leagues are harder to forecast than E0 and D1 (market 1.01 to 1.06 against 0.97), and the market beats Elo-country and DC-country in every row. On validation at `pre` it leads Elo-country by 0.008 in D2, 0.012 in E1 and 0.023 in E2, against 0.016 for `elo-v1` in E0 and D1: the gap is narrower only in D2.

### Criterion 2b, as pre-registered

Base model: `elo-country-v1`, development log loss at `pre` 1.0562 against 1.0572 for `dixon-coles-country-v1` (19,740 matches, three leagues), so the test uses `market-elo-country-v1`. Blend minus market on validation, paired, 99% interval from 10,000 bootstrap draws over matchdays:

| League | Horizon | n | Market | market-elo-country − Market | Pass |
|---|---|---|---|---|---|
| D2 | pre | 1,224 | 1.0458 | +0.0000 (−0.0020, +0.0020) | no |
| D2 | close | 1,224 | 1.0438 | +0.0013 (−0.0027, +0.0053) | no |
| E1 | pre | 2,208 | 1.0461 | +0.0014 (−0.0006, +0.0034) | no |
| E1 | close | 2,208 | 1.0453 | +0.0013 (−0.0003, +0.0029) | no |
| E2 | pre | 2,055 | 1.0146 | −0.0017 (−0.0036, +0.0002) | no |
| E2 | close | 2,056 | 1.0104 | −0.0008 (−0.0020, +0.0005) | no |

`market-dc-country-v1`, not tested, gives the same picture: −0.0015 (−0.0034, +0.0002) for E2 at `pre`, every interval holding 0. Without `pre_timing_uncertain` matches (pre only): D2 −0.0001, E1 +0.0011, E2 −0.0016 (−0.0035, +0.0004). No conclusion changes. On development the blends are worse than the market in every league and horizon, 0.001 to 0.004, the interval clear of 0 in four of six rows.

Where E2's small gain comes from: the fitted weight on Elo-country is negative in E1 and E2 in every season from 2017/18 (−0.04 to −0.12 at `pre`), so the blend moves away from our model where it disagrees with the market. What it keeps is a recalibration of the market: in E2 `a` is 1.13 to 1.20 at `pre` (the market is too cautious), in D2 `c_draw` about +0.07 (it underrates draws). The same recalibration in E0 and D1 did not survive out of sample; here it comes close in E2 but does not pass.

### Margin: is the market thinner, and do costs eat it?

Mean bookmaker margin per match, validation, `pre`:

| Bookmaker | E0 | D1 | E1 | E2 | D2 |
|---|---|---|---|---|---|
| bet365 | 5.4% | 5.4% | 5.3% | 5.0% | 6.0% |
| Pinnacle | 2.7% | 2.8% | 3.0% | 3.8% | 3.2% |
| William Hill | 5.6% | 5.9% | 6.3% | 7.4% | 7.6% |
| Interwetten | 5.2% | 5.2% | 6.6% | 9.3% | 5.9% |

Thinner, a little: the sharp bookmaker (Pinnacle) and the soft ones charge 0.3 to 4 points more in the lower leagues, while about as many bookmakers, six, price each match (`docs/data-sources.md`). But bet365, the executable bookmaker, charges the same 5 to 6% as in E0 and D1. With the 5.3% tax a bet costs about 10% of the stake. The best point estimate, 0.0017 in log loss in E2, is a fraction of a percent in probability, far below 10 points of costs; and it is a recalibration of the market, not information from our models.

### Verdict against the stop rule

No league passes at either horizon: every 99% interval holds 0; three of six point estimates are worse than the market, one equal. By the pre-registered stop rule the betting question (questions 2 to 4) is closed for good: no CLV or profit test, no paper trading. The project moves to EURO 2028 forecasting. No holdout run is made.

## 2026-09-28: national-elo-v1, the tournament spec's MODEL step

Data seen: warm-up and development (men's internationals from 1872 to 2019-12-31). Validation (2020-01-01 to 2024-07-14) and the holdout (WC 2026) are not scored; a count-only check confirms 166 validation and 104 holdout finals matches, never read further. Rules and periods: `docs/tournament-spec.md`.

Model (`src/football_forecasting/national_elo.py`):

- `national-elo-v1`: one Elo rating per team, starting at 1500, updated after every international, walk-forward. K by tournament type, eloratings.net's published weights (Wikipedia, World Football Elo Ratings, checked against the site's own numbers): 60 World Cup finals, 50 continental championship and intercontinental finals (EURO, Copa América, the African and Asian Cups, the Gold Cup, the Confederations Cup), 40 qualifiers and Nations Leagues, 20 friendlies, 30 everything else. Rating change also scaled by eloratings.net's goal-difference multiplier (1 for a draw or one-goal win, 1.5 for two goals, `(11 + goals) / 8` for three or more). Home advantage 100 points, added only when `neutral` is false: checked that this is exactly the host's own matches at a WC or EURO finals (7 of 51 EURO 2016 matches are non-neutral, all France's; 3 of 64 WC 2010 matches, all South Africa's). Awarded matches (Italy v Serbia, 2010-10-12, forfeited 3-0) update no rating.
- Ratings map to 90-minute H/D/A by elo-v1's ordered logit on the rating gap, refit before each WC or EURO finals tournament on every earlier finals match with a reliable 90-minute score, then held fixed for that tournament's own matches (`TournamentLogit`), so a semi-final forecast never learns from that tournament's own group stage through the logit (ratings still do, by design, since they update after every match).
- Benchmarks: `naive-tournament-v1` (H/D/A base rates from earlier finals matches, split by whether the host plays) and `eloratings-v1` (eloratings.net's own published pre-match ratings, run through the same kind of ordered logit, fit on the same matches).

Settings tried on development only (`uv run research/national-elo-tuning/choose.py`), tournament log loss (the 369 development finals matches), home advantage fixed at 100 except where varied:

| K | home advantage | log loss, tournament | log loss, all competitive |
|---|---|---|---|
| eloratings.net tiered | 60 | 0.9781 | 0.8705 |
| eloratings.net tiered | 80 | 0.9783 | 0.8689 |
| eloratings.net tiered | 100 (stored) | 0.9788 | 0.8689 |
| eloratings.net tiered | 150 | 0.9813 | 0.8749 |
| flat K = 30 | 100 | 0.9723 | 0.8676 |
| flat K = 40 | 100 | 0.9693 | 0.8685 |
| flat K = 50 | 100 | 0.9690 | 0.8704 |
| eloratings.net tiered, G off (= 1) | 100 | 0.9894 | 0.8731 |

A flat K of 30 to 50 scores close to, and at some values a little better than, the tiered scheme on both sets: the best point estimate is 0.9690 on the tournament set (K = 50, 0.0098 below tiered) and 0.8676 on the wider set (K = 30, 0.0013 below tiered). The ranking does not hold across both sets, though: K = 50 is 0.0015 worse than tiered on the wider set, and every gap here is small against a 369-match sample. Kept the tiered, published scheme: the tournament spec asks for K "by match importance," and no flat value beats it clearly and consistently enough to justify departing from that design. Home advantage 60 to 100 moves the score by 0.0007 at most, inside noise; kept eloratings.net's own 100, not the club model's 60, since it is the published value for this exact method. Turning the goal-difference multiplier off costs 0.0106 on the tournament set and 0.0042 on the wider one, worse both times: a real, kept feature, not noise.

Stored: `national-elo-v1` (home advantage 100, eloratings.net's tiered K, eloratings.net's G), `naive-tournament-v1`, `eloratings-v1`.

Development scores (`mise run national-elo:backtest`), on the matches all three models predicted:

| Set | n | national-elo-v1 | naive-tournament-v1 | eloratings-v1 |
|---|---|---|---|---|
| tournament (WC/EURO finals) | 369 | 0.9788 | 1.0880 | 0.9793 |
| all competitive, development | 5,288 | 0.8688 | 1.0816 | 0.8675 |

RPS: 0.1963 (tournament) and 0.1641 (all competitive) for national-elo-v1, against 0.2340 and 0.2300 for naive, 0.1948 and 0.1640 for eloratings-v1.

Paired differences in log loss, national-elo-v1 minus each benchmark, 95% bootstrap interval over 10,000 draws blocked by match day:

| Set | minus naive-tournament-v1 | minus eloratings-v1 |
|---|---|---|
| tournament | -0.1092 (-0.1502, -0.0667) | -0.0005 (-0.0164, +0.0152) |
| all competitive | -0.2128 (-0.2315, -0.1937) | +0.0013 (-0.0031, +0.0054) |

Calibration (5 bins), tournament matches (369, so most bins are small): home and away wins track the diagonal in the well-filled bins (away 47.3% forecast against 50.0% observed on 80 matches; home 49.8% against 52.3% on 107) and drift more in the thin ones (home's top bin, 9 matches, 85.1% forecast against 55.6% observed). Draws sit in only the bottom two bins, since national-elo-v1 never gives one above 40%; the well-filled bin (322 of 369 matches) is close, 27.8% forecast against 25.8% observed. With 369 matches split three ways across 5 bins, most cells are too small to read much into on their own. The wider competitive set (5,288 matches, so 10 to 100 times the count per bin) tracks the diagonal closely throughout.

**Reading.** national-elo-v1 clearly beats naive on both sets, the interval well clear of 0. It ties eloratings.net's own ratings almost exactly: -0.0005 on the tournament matches and +0.0013 on the wider set, both intervals holding 0 in the middle. This is the expected result for question 1 of the tournament spec ("yes to 1 against eloratings.net, same method"): the two methods are close enough in design that matching scores confirms the engine, not a new finding. The gap to beat is the market's, once odds are loaded; that is a later step.

Immutable storage: `save()` in `src/football_forecasting/national_elo_backtest.py`, the same discipline as `backtest.save` (hash-based `prediction_id`, a rerun stores nothing new, a changed value for a stored id raises), in its own tables (`international_predictions`, `international_runs`) since this schema carries no horizon or odds. `match_probs(team_a, team_b, home_team_or_none, as_of)` is the simulator's interface; it caches the walk-forward build per `as_of` and is capped at the end of development by `national_elo.load`'s default until a review authorizes scoring validation.

Stop, per the task: development only. Validation and the holdout are untouched beyond the two counts above.
