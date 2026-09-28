# Tournament spec

Second milestone of the project. The league experiments closed the betting question: for E0, D1, D2, E1 and E2 no model adds information to the market (`docs/experiment-log.md`, thin-market verdict). The project now forecasts national-team tournaments, with EURO 2028 (9 June to 9 July 2028, UK and Ireland) as the live target. These rules are written before any international data is loaded, so success cannot be redefined after the results come in.

Status: draft 2026-09-28, not frozen. Changes go in the change log with a date and a reason.

## Questions

Three questions, in order. Each one only matters if the one before it holds.

1. **Match:** does our model predict 90-minute H/D/A in tournament matches as well as the eloratings.net ratings, and close to the market where odds exist?
2. **Tournament:** are its probabilities of reaching each round calibrated, and better than a naive benchmark?
3. **EURO 2028:** can it publish probabilities for every team before and during qualifying, logged before each match and scored afterwards?

Expected answer: yes to 1 against eloratings.net (same method), a small gap to the market, unknown for 2. Question 3 is a build, not a test; its scores come in July 2028.

## Scope

| | In | Out |
|---|---|---|
| Teams | men's senior national teams | women, youth, club teams |
| Scored matches | World Cup and EURO finals; EURO 2028 qualifiers (prospective) | friendlies, other confederations' tournaments (these update ratings only) |
| Targets | 90-minute H/D/A, reaching each round, winning; qualifying for EURO 2028 (prospective) | exact score, goalscorers, over/under |
| Data | results, venues, goal minutes, shootouts, eloratings.net ratings, odds | lineups, player ratings, club form, injuries, xG |
| Models | naive, national-team Elo with an ordered logit, eloratings.net ratings, market | goal models, ensembles, market-aware blends |
| Money | none | bets; the betting question stays closed |

## Data

| Need | Source | Cost |
|---|---|---|
| Results since 1872, venue, neutral flag | martj42/international_results (`results.csv`), CC0 | free |
| Goal minutes (for 90-minute scores), shootouts | same repo (`goalscorers.csv`, `shootouts.csv`) | free |
| Published ratings, benchmark 2 | eloratings.net `.tsv` files | free, terms not found |
| Match odds and World Cup winner odds, June 2020 on | The Odds API, historical endpoints | one month of a paid plan, ~11,000 credits: the 20K plan, $30 once |
| Live odds for EURO 2028 qualifiers and finals | The Odds API | $30/mo while qualifiers run, or one month per window |
| Tournament formats | UEFA and FIFA regulations, typed in by hand as a seed | free |

Facts that shape the spec, with sources in `docs/data-sources.md`:

- martj42 scores include extra time and exclude shootouts. The 90-minute score comes from `goalscorers.csv`, which has a `minute` column; a knockout match that went to extra time was a draw at 90 minutes, whoever won it
- martj42 uses the team's current name for all its history (Northern Ireland for the 1882 "Ireland"), and `neutral` says whether the match was at a neutral venue
- The Odds API: no friendlies key. Earliest match odds: EURO key 2021-05-19 (EURO 2020 played from 11 June 2021), World Cup 2022-04-03, Nations League 2022-06-11, EURO qualifying 2023-10-12, World Cup qualifying Europe 2025-03-24. Earliest World Cup winner odds 2022-03-29; no EURO winner odds listed
- So odds cover four tournaments: EURO 2020, WC 2022 and EURO 2024 (validation) and WC 2026 (holdout); and the EURO 2028 qualifiers live
- Pinnacle closed its public API on 23/07/2025, so WC 2026 odds may lack a sharp bookmaker; the benchmark is the median across bookmakers

## Targets

For each scored match, `P(Home), P(Draw), P(Away)` at 90 minutes (stoppage time included, extra time and penalties excluded), summing to 1. At neutral venues "home" is the team listed first; log loss and RPS do not depend on which team that is.

For each team in a tournament, `P(reach round r)` for every round after the group (for a 24-team EURO: round of 16, quarter-final, semi-final, final, winner), and `P(win)`. For EURO 2028 only, also `P(qualify)`.

Horizons:

- Match `pre`: 24 hours before kickoff; the model uses only matches finished before that. The Odds API snapshot at the same time
- Match `close`: the last Odds API snapshot before kickoff; the model forecast stays the `pre` one
- Tournament: after the final draw and before the first match, with every match up to then known
- Knockout matches: the simulator's own forecast of a tie (extra time, penalties) is used inside the simulator only; the scored target is the 90-minute result

Martj42 gives dates, not kickoff times; kickoff comes from The Odds API where it has the match, else the day before the match date counts as the horizon.

## Data periods

| Period | Dates | Scored | Use |
|---|---|---|---|
| Warm-up | before 2006-01-01 | nothing | fit ratings only, EURO 2004 included |
| Development | 2006-01-01 to 2019-12-31 | WC 2006, 2010, 2014, 2018; EURO 2008, 2012, 2016 (369 matches) | walk-forward, free to iterate |
| Validation | 2020-01-01 to 2024-07-14 | EURO 2020 (played 2021), WC 2022, EURO 2024 (166 matches) | pick the model; odds exist |
| Holdout | 2024-07-15 to 2026-07-19 | WC 2026 (104 matches, 48 teams) | locked, run exactly once |
| Prospective | after the spec is frozen | EURO 2028 qualifiers and finals | predictions logged before kickoff |

Every match, friendlies and all confederations included, updates ratings in every period; only the matches in the table are scored. For tuning on development, all competitive matches (not friendlies) in the period may also be scored, reported apart from the tournament matches.

Matches between the WC 2026 final and the freeze update ratings but are never scored.

Walk-forward: ratings update after every match, never with a later one.

## Benchmarks

1. **Naive:** H/D/A base rates from earlier tournament matches, split by whether a host plays; for rounds, every team equally likely under the format (16 of 24 reach the round of 16)
2. **eloratings.net:** its published pre-match ratings, turned into H/D/A by the same ordered logit as our model, fitted on the same matches; for rounds, the same ratings run through our simulator
3. **Market:** The Odds API, devigged by normalization, median across bookmakers, at `pre` and `close`; for the winner, World Cup winner odds before WC 2022 and WC 2026

## Metrics

| Role | Metric |
|---|---|
| Primary match | log loss |
| Secondary match | RPS, calibration curve |
| Primary rounds | Brier over every team and round |
| Secondary rounds | log loss (probabilities clipped at 1 / (2 × runs)), calibration curve and slope |
| Winner | log loss of the champion's probability, Brier over all teams; reported, no pass or fail |

Brier leads for rounds because a simulated probability can be 0, and log loss then depends on the clipping rule.

Confidence intervals: 95%, paired bootstrap, 10,000 draws. Matches: blocks by match day. Rounds: blocks by team within tournament (all of one team's rounds together).

## Success criteria

Judged on the holdout (WC 2026); validation picks the model. `X` values are open decisions.

| # | Pass if (holdout) |
|---|---|
| M1 | model log loss below naive, CI excludes 0 |
| M2 | model minus eloratings.net log loss: upper bound below `X1` |
| M3 | model minus market (`pre`) log loss: upper bound below `X2` |
| R1 | rounds Brier below naive, CI excludes 0 |
| R2 | calibration slope on rounds: CI holds 1, point within 1 ± `X3` |

The samples are small: 104 holdout matches and 166 validation matches, against 1,200 to 2,200 per league in the thin-market test, so intervals will be about three to five times as wide. Set `X1` to `X3` with that in mind. Three validation tournaments give three winners, so the winner metrics cannot decide anything.

## Decisions that follow

- Fail M1 or R1: fix the model or the simulator before anything else
- Pass M1, fail M2: our Elo is worse than a free published one; the dashboard uses eloratings.net ratings through our simulator
- Pass M1 and M2, fail M3: the dashboard publishes, with the market shown beside our numbers where odds exist
- Fail R2 with M passing: check the simulator (formats, tie-breakers, extra time) against past brackets before trusting round probabilities
- Pass all: the dashboard publishes as is. The EURO 2028 prospective log is the next test; there is no second holdout

## Simulator

- Formats are data: group sizes, tie-breaker order (WC: goal difference first; EURO: head-to-head first), best third-placed rules and the table that places them in the bracket, extra time, penalties
- 10,000 runs per forecast, seeded; seed and code version stored with each forecast
- Before any score: fed the real results of each past tournament, it must reproduce the real group tables and bracket. A test checks this for every development and validation tournament
- Scores: the ordered logit gives H/D/A only, but tie-breakers need goals. Each run draws the outcome from the model, then a score from earlier tournament matches with that outcome
- After a 90-minute draw in a knockout match, each team goes through with its share of the model's win chances, `P(H) / (P(H) + P(A))`; extra time and penalties are not modelled apart unless development data shows they should be

## Rules against fooling ourselves

- Every model and simulator version tried goes in `docs/experiment-log.md`, with the date and the data period it saw
- At most three model versions scored on validation; the holdout sees one
- WC 2026 is already played and its results are known to the author in outline. No choice may rest on them: scoring code refuses matches after 2024-07-14 until the holdout run, and the holdout odds are bought only for that run
- A second holdout run counts as a new experiment and needs a new tournament, which means EURO 2028
- Predictions are stored immutable: `prediction_id, match_id, prediction_as_of, model_version, p_home, p_draw, p_away, odds_*`; tournament forecasts likewise, with `team, round, p, runs, seed, format_version`
- Team names: one seed maps martj42, eloratings.net and The Odds API names to one id; a test fails on any unmapped team in a scored match. Successor states (such as Serbia and Montenegro to Serbia) follow martj42, fixed before development
- Prospective forecasts are logged before kickoff and never edited; a model change starts a new version, and the old one keeps scoring

## Open decisions

- [ ] `X1`: allowed gap to eloratings.net in log loss
- [ ] `X2`: allowed gap to the market in log loss
- [ ] `X3`: allowed departure of the calibration slope from 1
- [ ] Rounds metric: Brier primary (proposed) or log loss
- [ ] Odds purchase: one month for validation now, one more for the holdout run (proposed), or one month for all four tournaments
- [ ] `P(qualify)` for EURO 2028: scored as a target (proposed, one run, about 55 teams) or shown only
- [ ] eloratings.net: no terms found; use for private research as for Understat, or ask first

## Change log

- 2026-09-28: first draft
