# Post-mortem

Written 2026-09-29. Covers everything up to open PR #11 (`feat/euro-2028`). Sources: `docs/experiment-spec.md` (the spec), `docs/tournament-spec.md` (the tournament spec), `docs/experiment-log.md` (the log), `docs/data-sources.md` and the README. Parentheses name the section. The round-calibration diagnosis in the log and the EURO 2028 section of `docs/data-sources.md` are on PR #11, not yet on master.

## What we set out to do

Forecast football matches with statistical models and test whether the forecasts beat the betting market after costs. Four questions, each only worth asking if the one before holds: beat Elo, beat or add to the market, beat the closing line, make money after the bookmaker's margin and German betting tax (spec, Questions). The second, pre-registered test added an exit: if it failed, the project would switch to forecasting EURO 2028 (spec, Change log).

## How we tested it

We wrote and froze both specs before loading any data for them, with pass rules, periods and confidence intervals fixed in advance.

- **Leagues:** E0 and D1 first. Warm-up 2000/01 to 2004/05, development 2005/06 to 2018/19, validation 2019/20 to 2022/23, holdout 2023/24 to 2025/26, locked for one run (spec, Data periods). Criterion 2b asked whether a blend of market and model beats the market alone, with a confidence interval that excludes 0 (spec, Success criteria). After E0 and D1 failed, we pre-registered a second test on D2, E1 and E2 with a stop rule: if no league passes at either horizon on a 99% interval, the betting question closes for good (spec, Change log).
- **Tournaments:** development covers seven WC and EURO finals from 2006 to 2019 (369 matches), validation EURO 2020, WC 2022 and EURO 2024 (166 matches), and the holdout WC 2026 (104 matches), run once (tournament spec, Data periods). Five criteria, all on the holdout: M1, log loss below naive with the interval excluding 0; M2, the interval's upper bound against eloratings.net below 0.02; M3, the same against the market below 0.04; R1, round Brier below naive with the interval excluding 0; R2, a round calibration slope from 0.7 to 1.3 whose interval holds 1 (tournament spec, Success criteria).

## What came out

**Leagues: no model adds information to the market.** The market beats Elo in all 18 pre-match seasons (log, Phase 2 engine). Poisson and Dixon-Coles tie Elo (log, Phase 3). The market-aware blends give our model a weight near 0 and score no better than the market on validation, every interval holding 0 (log, question 2b). Shots and rest days add nothing; xG beats Dixon-Coles by 0.0019 on validation, though not on development, and still trails the market by 0.012 to 0.015 (log, Phase 4 answers). In the thinner leagues no league passes at either horizon; the best point estimate, E2 at `pre`, is −0.0017 with a 99% interval of −0.0036 to +0.0002 (log, thin markets, Criterion 2b). bet365 charges 5 to 6% there too, so with the 5.3% tax a bet costs about 10% of the stake (log, thin markets, Margin). No league passed, so the stop rule closed the betting question: no CLV or profit test, no paper trading, no league holdout run (log, thin markets, Verdict). An earlier look at betting rules on development lost money under every rule, from 9.2% per unit for backing the favourite to 41.3% for the market model's biggest edges (log, first look at the betting rule).

**Tournaments: our Elo beats naive and ties eloratings.net, except on the holdout.** `national-elo-v1` minus eloratings.net was −0.0005 on development and −0.0001 on validation (log, the tournament spec's MODEL step; validation). Against naive it led by 0.109 on development, and by 0.064 on validation, where the interval still held 0 (same sections). On WC 2026 (log, HOLDOUT RUN, Success criteria):

| # | Reading | Verdict |
|---|---|---|
| M1 | −0.1781 (−0.2576, −0.0901) against naive | pass |
| M2 | +0.0086 (−0.0102, +0.0275) against eloratings.net | fail |
| R1 | −0.0500 (−0.0820, −0.0229) against naive | pass |
| R2 | slope 1.387 (1.102, 1.874) | fail |
| M3 | no odds bought | not run |

By the pre-set rule, M2 failing moves the dashboard to eloratings.net ratings through our simulator. R2 says the round probabilities were too cautious on WC 2026. On development the same simulator gives a slope of 0.927 for eloratings-v1 and 0.994 for national-elo-v1, and two fixes changed little, so we kept none and the simulator stays `sim-v1` (log, round-calibration diagnosis). M3 never ran because we never bought The Odds API data: the tournament spec planned one month of the 20K plan ($30) for validation and one more for the holdout (tournament spec, Data; Open decisions). It can still run on the stored holdout predictions (log, HOLDOUT RUN).

## What worked

- **Pre-registration.** Every verdict follows a rule written before the data. The stop rule turned "maybe the lower leagues" into one test with a fixed end.
- **Immutable predictions.** Each prediction has a hash-based id; storing a new value under an old id raises an error (log, the tournament spec's MODEL step). Stored scores cannot change; the source data can (see below).
- **dbt tests.** They pin down facts we would otherwise have assumed: odds timing, the 90-minute score, team-name maps, Understat match joins (`docs/data-sources.md`).
- **Holdout discipline.** We never loaded the league holdout. The WC 2026 holdout ran once, and the R2 diagnosis went back to development instead of tuning on the holdout. One caveat: the author knew the WC 2026 results in outline, which is why the scoring code refused post-validation matches until the run (tournament spec, Rules against fooling ourselves).
- **Benchmarks as checks.** The naive model's winner log loss landed near the uniform value for each field size, which showed the naive benchmark was wired right (log, validation, Winner).

## What did not work, or cost time

- **Features from past matches.** Goal models, shots and xG all trailed the market by 0.012 to 0.018, most likely because the market knows team news we lack (log, Phase 3; Phase 4 answers).
- **Data checks.** Odds collection times, UK kickoff times, stoppage time in goal minutes, match dates one or two days apart between sources, and fair-play overrides in the bracket replay each needed its own check (`docs/data-sources.md`; log, validation).
- **Small tournament samples.** 104 holdout matches and one 48-team bracket make M2 and R2 noisy. The spec warned of this; the bounds still decided the result.
- **Understat.** We downloaded xG against its robots.txt, by the owner's choice (`docs/data-sources.md`, Understat), for a gain of 0.0019 on validation only (log, Phase 4 answers).
- **M3 stays open.** Nobody approved the spend, so the one test against the market in tournaments has no answer.

## What we would do differently

In our view, not tested:

- Measure the gap from Elo to the market first, before building goal models and features. A gap of 0.016 in E0 and D1 (tournament spec, Success criteria) was a strong early sign.
- Buy the tournament odds when the spec is frozen, or drop M3 from it.
- Judge R2 on more than one bracket, or report it without a pass or fail, as the spec already does for the winner.
- Do not download against a source's stated terms.

## How it closed

The project was archived on 2026-09-29. The dashboard container, its Caddy route and the `football.pascalkraus.com` DNS record were removed; the dashboard, the EURO 2028 page included, now runs only locally (`mise run dashboard`). The GitHub repo is archived and read-only.

- `mise run euro2028:refresh` still works locally: it downloads martj42 and eloratings.net again, rebuilds dbt and logs a new ratings snapshot. eloratings.net rewrites past years, so check the `dbt/seeds/eloratings_files.csv` diff before trusting a changed forecast (`mise.toml`).
- For a restart: the EURO 2028 qualifying draw is on 6 December 2026 in Belfast (`docs/data-sources.md`, EURO 2028 qualifying). Forecasting qualifying needs new code (home and away groups, `P(qualify)`); if round probabilities are too cautious again, rating uncertainty is the next thing to try (log, round-calibration diagnosis).
- On 2026-09-29 the league tables were missing from `data/predictions.duckdb`: an agent had put a copy holding only the international tables in its place. We rebuilt the file from the backup `predictions.pre-thin.duckdb` and a rerun of the backtest. No stored E0 or D1 prediction changed, and every D2, E1 and E2 validation score matches the log to four places; only the stored-at times and run ids of the lower-league rows date from the rebuild. `data/` is not in git, so a store like this needs its own backup.

## What comes next

A Kicktipp tipping test on the World Cup and EURO, as a new project: the market is an input there, not the opponent, and the tip that earns the most points on average under a pool's rules can be worked out from score probabilities. Kicktipp's rule options were surveyed on 2026-09-29 (fixed points, goal distance, a rule that pays more for rare tips, knockout tips at 90 minutes, after extra time or after penalties, bonus questions, jokers). The test needs the pool's own settings and its own spec, frozen before any data, like the two before it.
