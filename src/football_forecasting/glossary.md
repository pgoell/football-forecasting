# Glossary

What the words on the Backtest page mean, and how each model works. The rules behind all of this are in `docs/experiment-spec.md` in the repo.

## The forecast

Each model gives every match three chances that add up to 100%: **home win**, **draw** and **away win** (together called 1X2). Nothing else is forecast: no scores, no goal counts.

**Backtest.** Replaying past seasons match by match, as if each forecast were made at the time. A model may use only results and odds that were known before the forecast; it never sees later matches. Using later information by mistake is called **leakage**, and it makes a model look better than it is. The engine is built so that leakage cannot happen, and tests check it.

## Seasons

The seasons are split up front, so a good result cannot come from tuning on the very seasons it is judged on.

| Name | Seasons | Use |
|---|---|---|
| Warm-up | 2000/01 to 2004/05 | builds up ratings; never scored |
| Development | 2005/06 to 2018/19 | free to try ideas and tune models on |
| Validation | 2019/20 to 2022/23 | picks the final model and betting rule; look sparingly |
| Holdout | 2023/24 to 2025/26 | locked; scored exactly once at the end, never shown here |

Every model still learns from all earlier matches as it goes: a forecast in 2015 uses everything up to that point, in every period.

## When the forecast is made

**Pre-match.** When Football-Data records the odds: Friday 17:00 UK time for games from Friday to Monday, Tuesday 13:00 for games from Tuesday to Thursday (15:00 before 2017/18). That is about 1 to 3 days before kickoff. Team news that comes later (injuries, line-ups) is not in these forecasts.

**Closing.** At kickoff, with the last odds before the game. Before 2019/20 the files have no kickoff times, so the closing forecast is placed at the end of the match day, and no result from that day counts as known.

**Skip 20 Dec to 5 Jan.** Around Christmas and New Year the pre-match odds may have been recorded later than the usual Friday or Tuesday. Leaving these matches out checks that the results do not depend on them. It only affects pre-match forecasts.

Closing odds exist only from 2012/13, and until 2018/19 only from Pinnacle. So in Development with closing forecasts, the market model covers 2012/13 to 2018/19 and uses Pinnacle alone.

## Scores

Lower is better for all three. Football is mostly luck, so even the best forecast scores far from perfect, and good models sit close together.

| Score | What it measures | Perfect | Guessing ⅓ each |
|---|---|---|---|
| **Log loss** (main score) | minus the log of the chance given to the result that happened | 0 | 1.099 |
| **Brier** | squared error of the three chances, against 1 for the result and 0 for the others | 0 | 0.667 |
| **RPS** (ranked probability score) | like Brier, but treats the results as ordered (home, draw, away), so a draw costs a home win forecast less than an away win does | 0 | about 0.22 |

**Reading log loss.** If a model gave the actual result 40%, that match costs −ln(0.40) = 0.92; at 20% it costs 1.61. Log loss punishes confident mistakes hard. The market scores about 0.97, so on average it gave the actual result about 38%. A gap of 0.01 between two models is large.

**Matches.** Each model is scored only on matches that all chosen models forecast, so the numbers compare like with like. Adding or removing a model can change the match count, and with it the numbers.

**Gap to a reference.** One model's log loss minus another's in the same season. Seasons differ in how predictable they are, which moves every model up or down together; the gap removes that. A model below 0 season after season really beats the reference.

**Calibration.** Whether the chances mean what they say. Forecasts are grouped by the chance given (0 to 10%, 10 to 20%, ...), and each group's average chance is set against how often that result happened. On the diagonal, a 40% forecast comes true 40% of the time. Above the diagonal the model was too cautious; below it, too confident. A model can be well calibrated and still poor: always saying the league's average rates is calibrated but tells you nothing about the match.

## Models

A model's name ends in a version, such as `-v1`. Stored forecasts never change, so a model whose forecasts change must get a new version.

### naive

How often home wins, draws and away wins happened in the same league in all earlier seasons. Every match in a season gets the same forecast, roughly 47% home, 25% draw, 28% away. It knows home advantage exists and nothing about the teams. The floor any real model must clear.

### elo

A rating per team, the method first used for chess players.

- Every team starts at 1500 in 2000/01. After each match the winner takes points from the loser; how many depends on how surprising the result was. Beating a much stronger team gains a lot; beating a weak one gains little. A draw moves points toward the weaker team.
- **K = 20**: the largest number of points one match can move.
- **Home advantage = 60**: the home team is treated as 60 points stronger when working out how surprising a result was.
- **Promoted teams** start at **1400**, the average rating of relegated teams in the warm-up seasons, since promoted teams tend to be about as strong as the teams they replace. Ratings otherwise carry over from season to season.
- **From ratings to chances.** The rating gap between the teams is turned into home, draw and away chances by a small fitted formula (an ordered logit): the bigger the gap, the likelier the stronger team wins and the less likely a draw. The formula is refitted at the start of each season on all earlier matches.

K and home advantage were set by hand, not tuned. Elo knows nothing about injuries, line-ups or transfers; it learns only from results.

### market-consensus

What the bookmakers think.

- **Odds to chances.** Odds of 2.00 mean a 50% chance, 4.00 mean 25%. Bookmakers' chances add up to more than 100% (say 105%); the extra is their margin. Dividing each chance by the total removes it (called **devigging**).
- **Consensus.** Take the middle value (median) of each chance across bookmakers, then scale the three to add up to 100%.
- **Which bookmakers.** Only single bookmakers, not the averages and maximums the files also carry. Pinnacle is left out from 23 July 2025, when its prices became unreliable.
- It uses the odds of the chosen forecast time: pre-match odds for pre-match forecasts, closing odds for closing ones.

The market is the bar to beat. Beating it clearly would more likely point to a bug or leakage than to a real edge.

## Runs

**Run.** One execution of the backtest. Each run adds a row per model with the code version (commit), whether that code had uncommitted changes, the model's settings, and the seasons it read.

**New forecasts.** Forecasts a run stored for the first time. A rerun of unchanged models reproduces the stored forecasts exactly and stores nothing new; each forecast keeps the run that first stored it.
