# Data sources

Where the data comes from, what each fact about it rests on, and how to check it again. Every quote was fetched on 2026-09-28; the archive link is a copy of the page taken the same day, so the quote stays checkable if the page changes.

Status per fact:

- **checked**: read on the source page, quoted here
- **tested**: a dbt test checks it on every build
- **unverified**: reported by a research agent or inferred; not confirmed

## Reproduce the data

```sh
mise run data:download            # 135 CSVs into data/raw/football-data/
mise run data:download:understat  # 26 JSON files into data/raw/understat/
mise run data:download:international-results  # 4 CSVs into data/raw/international-results/
mise run data:download:eloratings  # 26 TSV files into data/raw/eloratings/
git diff dbt/seeds/*_files.csv
mise run dbt:build
```

`dbt/seeds/football_data_files.csv` records the sha256 of every stored CSV that the repo was built with. After a download, the diff shows which files differ; the running season's file changes with every matchday, past seasons should not. The dbt test `data_files_match_recorded_version` warns when the files on disk do not match the record.

The download stores each file as UTF-8 with Unix line endings. D1 2000/01, D1 2001/02 and E0 2004/05 come as Windows-1252; D1 2024/25 onward and E0 2021/22 and 2024/25 onward start with a BOM. `data/raw/football-data/_manifest.jsonl` keeps the sha256 of the bytes as downloaded. Test: `team_names_decoded`.

## Football-Data

Site: <https://www.football-data.co.uk>. Files: `https://www.football-data.co.uk/mmz4281/<ssss>/<league>.csv`, `ssss` = `2526` for 2025/26, league as in `dbt/seeds/leagues.csv`: E0, E1, E2, D1, D2 (the last three since 2026-09-28, for the thin-market experiment in `docs/experiment-spec.md`).

### Pre-match odds collection time (checked, tested for plausibility)

> "Please note that the odds are collected for the downloadable weekend fixtures on Fridays afternoons generally not later than 17:00 British Standard Time. Odds for midweek fixtures are collected Tuesdays not later than 13:00 British Standard Time."

Source: <https://www.football-data.co.uk/matches.php>, archived <https://web.archive.org/web/20260928135512/https://football-data.co.uk/matches.php>.

`int_odds.available_at` for `pre` uses this rule: matches Friday to Monday get Friday 17:00 UK time, Tuesday to Thursday get Tuesday 13:00 (15:00 before 2017/18, see below), capped at kickoff. With kickoff times (2019/20 onward) that gives a median lead of 22h and a maximum of 75h; one Tuesday 12:30 kickoff hits the cap. Test: `pre_odds_lead_time_plausible` (0 to 96h).

**Checked against archived copies** ([research/odds-timing/](../research/odds-timing/README.md), rerunnable):

| Period | Stated rule (archived `matches.php` / `notes.txt`) |
|---|---|
| 2003 to 2007 | "Friday afternoons" / "Tuesday afternoons", no clock time |
| Aug 2007 to May 2008 | fixtures "usually made available by Friday 15:00", midweek "by Tuesday 15:00" |
| Sep 2008 | weekend moves to "Friday 17:00 (2 hours later than previous on account of Betbrain's extra delays)" |
| by Sep 2011 | Friday "not later than 17:00", Tuesday "not later than 15:00" |
| Aug to Sep 2017 onward | Tuesday "not later than 13:00", and "generally" added to the Friday sentence |

- Odds never revised after the fact: in every archived copy, 2007/08 to 2026/27, odds equal the final files (high confidence). Earlier seasons only have copies taken after the season ended; those match too.
- No copy taken after the rule time lacked odds.
- Weekend, Friday 17:00: a safe upper bound in normal weeks. Before Sep 2008 the site said 15:00, so 17:00 is conservative there.
- Midweek before 2017/18: the site said Tuesday 15:00, so `int_odds` uses 15:00 for those seasons.
- 20 Dec to 5 Jan: a copy from 2015-12-28 04:27 UTC already held odds for Mon 28 to Wed 30 Dec as one batch, suggesting collection over the Christmas weekend, later than the modeled Fri 25 Dec 17:00 for the Monday games. No copy falls between 24 and 28 Dec to confirm it. `int_odds.pre_timing_uncertain` flags pre odds in this window (9,264 of 163,235 rows), so a backtest can leave them out or test with and without them.
- March 2020: 9 D1 games had odds for 13 to 16 March, were postponed, and appear in the final file on new dates with new odds. Expected.
- No before-kickoff copies at all for 2000/01 to 2003/04, 2008/09, 2009/10, 2012/13 and 2021/22 onward: the rule there rests on the stated wording alone.

### Pre-closing and closing odds (checked)

> "These are for pre-closing odds. For the closing odds, as below but with an additional "C" character following the bookmaker abbreviation/Max/Avg (e.g. B365CH = closing Bet365 home win odds)."

Source: <https://www.football-data.co.uk/notes.txt>, archived <https://web.archive.org/web/20260928135540/https://football-data.co.uk/notes.txt>.

> "Closing home-draw-away odds are also available for Pinnacle bookmaker only back to 2012/13). In earlier seasons, there are only the pre-closing odds."

Source: <https://www.football-data.co.uk/data.php>, archived <https://web.archive.org/web/20260928135406/https://football-data.co.uk/data.php>.

In our files, closing columns for all bookmakers start in 2019/20 and Pinnacle's (`PSC*`) in 2012/13. How close to kickoff "closing" is: not stated by the source (**unverified**). `available_at` for `close` is kickoff, or the end of the match day before 2019/20.

### Pinnacle unreliable since 23/07/2025 (checked)

> "Since 23/07/2025 Pinnacle's public API for odds delivery has become unreliable meaning their odds are systematically out of date relative to odds for other bookmakers, including both the pre-closing and closing odds. Consequently they should be used with caution when undertaking any betting analyses, and are no longer being included for the calculation of market average and maximum odds."

Source: <https://www.football-data.co.uk/data.php>, archived <https://web.archive.org/web/20260928135406/https://football-data.co.uk/data.php>.

`dbt/seeds/bookmaker_unreliable_periods.csv` holds the date; `int_odds.is_reliable` is false for Pinnacle from that match date (719 rows). Pinnacle fills only 210 of 380 E0 and 150 of 306 D1 matches in 2025/26 and is missing from 2026/27 (counted in our files).

### Kickoff times are UK time (inferred, tested)

notes.txt says only "Time = Time of match kick off". The Bundesliga's most common Saturday time in the files is 14:30, which is its 15:30 German-time slot, so times are UK local time. Test: `kickoff_times_are_uk_time`.

### D2, E1 and E2 (counted, tested)

Downloaded 2026-09-28, 2000/01 to 2026/27. Every finished season has 306 D2 or 552 E1 and E2 matches, except E2 2019/20 with 400: League One stopped in March 2020 and Bury, expelled before the season, played none. Test: `full_seasons_have_all_matches`, expected counts in `dbt/seeds/leagues.csv`. Team names match across leagues of a country: from 2001/02 to 2022/23 every E0, E1 and D1 team was in a covered league the season before, and E2 and D2 gain 2 to 5 teams a season from below.

Five bet365 pre-match rows (E1 Blackpool 27/04/2013, Brentford 02/02/2019; E2 Sheffield United 28/03/2015, Portsmouth 19/02/2019, Sunderland 05/12/2020) carry a home price of 0; `stg_football_data__odds` drops every row with a price of 1 or less (none in E0 or D1). Betfair Exchange pre-match prices in D2 and E2 (2024/25 onward, holdout and later) include margins up to 180%, likely stale exchange quotes; not traced, and outside the seasons the backtest loads.

Odds coverage, reliable non-aggregate bookmakers per match (median, and the lowest in the season at `pre`), and the median bookmaker margin at `pre`, averaged over matches. E0 and D1 for comparison. Seasons up to 2022/23; the holdout was not counted.

| League | Seasons | `pre` bookmakers, median (lowest) | `close` bookmakers, median | `pre` margin |
|---|---|---|---|---|
| D2 | 2000/01 to 2004/05 | 3 to 6 (1) | none | 11.7% to 14.0% |
| D2 | 2005/06 to 2011/12 | 8 to 10 (6) | none | 8.7% to 11.6% |
| D2 | 2012/13 to 2018/19 | 6 to 10 (4) | 1 (Pinnacle) | 6.3% to 7.9% |
| D2 | 2019/20 to 2022/23 | 6 (1) | 6 | 5.9% to 6.3% |
| E1 | 2000/01 to 2004/05 | 5 to 7 (3) | none | 11.5% to 12.6% |
| E1 | 2005/06 to 2011/12 | 9 to 10 (8) | none | 7.3% to 11.1% |
| E1 | 2012/13 to 2018/19 | 6 to 10 (3) | 1 (Pinnacle) | 4.2% to 6.7% |
| E1 | 2019/20 to 2022/23 | 6 (5) | 6 | 5.2% to 6.3% |
| E2 | 2000/01 to 2004/05 | 5 to 7 (3) | none | 11.6% to 12.3% |
| E2 | 2005/06 to 2011/12 | 9 to 10 (7) | none | 7.4% to 11.2% |
| E2 | 2012/13 to 2018/19 | 6 to 10 (5) | 1 (Pinnacle) | 5.3% to 6.6% |
| E2 | 2019/20 to 2022/23 | 6 (3) | 6 | 5.5% to 7.0% |
| E0, D1 | 2019/20 to 2022/23 | 6 (6) | 6 | 5.0% to 5.5% |

Flagged, too few bookmakers for a consensus (a median under 4, or matches priced by one or two):

- D2 2000/01 and 2001/02 at `pre` (median 3 and 4, some matches one bookmaker): warm-up, never scored
- every league at `close`, 2012/13 to 2018/19: Pinnacle alone, as in E0 and D1
- single matches: D2 2020/21 has one match with one bookmaker at `pre`, E2 2019/20 and E1 2018/19 matches with three

In the validation seasons the lower leagues have as many bookmakers as E0 and D1 (six at both horizons); the market is thinner in money traded, not in the count of prices, and its margin is about one point higher. The experiment keeps every flagged season (docs/experiment-spec.md).

### Shots and shots on target (tested)

> "HS = Home Team Shots / AS = Away Team Shots / HST = Home Team Shots on Target / AST = Away Team Shots on Target"

Source: <https://www.football-data.co.uk/notes.txt> (four lines, joined here), archived <https://web.archive.org/web/20260928135540/https://football-data.co.uk/notes.txt>. The same file does not say who counts shots or by what definition since 2002/03 (**unverified**).

Coverage in our E0 and D1 files, counted (D2, E1 and E2 not checked; no model uses their shots): every E0 season from 2000/01; D1 has no shots in 2002/03 and no shots on target from 2002/03 to 2005/06. D1 Union Berlin v Bochum on 14/12/2024, an awarded result, has none. Tests: `shots_coverage` (each season has them for every match or none, gaps as listed), `shots_on_target_within_shots` (warns: 3 E0 rows from the source have more shots on target than shots).

Shots count as known with the result (`result_at`).

### Rest days (derived)

`int_matches.home_rest_days` and `away_rest_days`: days since the team's previous match in the files; `home_matches_14d` and `away_matches_14d`: its matches in the 14 days before. Fixture dates are known in advance, so both are known before the match. The files hold league matches only, so cup and European games, the usual cause of short rest, are missing: in 60% of development matches both teams have the same rest, counting any break over a week as 8 days.

### Terms of use (unverified wording)

The research agent reported the site allows private, non-commercial use only. The exact wording was not re-checked.

## Germany

### Betting tax (checked)

> "Die Sportwettensteuer beträgt 5,3 Prozent der Bemessungsgrundlage nach § 17." (§ 18 RennwLottG)

> "Die Sportwettensteuer bemisst sich nach dem geleisteten Wetteinsatz abzüglich der Sportwettensteuer." (§ 17 (1))

> "Steuerschuldner ist der Veranstalter der Sportwette." (§ 19)

Sources: <https://www.gesetze-im-internet.de/rennwlottg_2021/__18.html> (archived <https://web.archive.org/web/20260928135706/https://www.gesetze-im-internet.de/rennwlottg_2021/__18.html>), [§ 17](https://www.gesetze-im-internet.de/rennwlottg_2021/__17.html) (archived <https://web.archive.org/web/20260928135633/https://www.gesetze-im-internet.de/rennwlottg_2021/__17.html>), [§ 19](https://www.gesetze-im-internet.de/rennwlottg_2021/__19.html) (archived <https://web.archive.org/web/20260928140050/https://www.gesetze-im-internet.de/rennwlottg_2021/__19.html>).

The bookmaker owes the tax. It is 5.3% of the stake net of the tax, which is 5.3 / 105.3 = 5.03% of the gross stake. The spec charges 5.3% of the stake, slightly above the legal rate, as the worse case.

**Unverified**: bet365 says it pays the tax itself rather than passing it on (<https://news.bet365.de/de-de/article/keine-wettsteuer-bei-bet365-fuer-deutschland-und-oesterreich/2025102812351653468>; the page blocks scripted access and the Internet Archive, so it is neither quoted nor archived). How bwin and Tipico pass it on: unverified.

### Licensed bookmakers (checked)

The GGL whitelist (<https://www.gluecksspiel-behoerde.de/de/fuer-spielende/uebersicht-erlaubter-anbieter-whitelist>, archived <https://web.archive.org/web/20260928135737/https://www.gluecksspiel-behoerde.de/de/fuer-spielende/uebersicht-erlaubter-anbieter-whitelist>) lists bet365.de, bwin.de, Interwetten, Tipico and Winamax. Pinnacle, Betfair and William Hill do not appear. `bookmakers.licensed_de` follows this.

**Unverified**: whether Football-Data's `B365`, `BW` and `IW` prices come from the German sites. Likely the international ones.

## Other sources (unverified)

From one research agent on 2026-09-28, checked on the providers' own pages by that agent but not re-checked:

| Source | Covers | Cost | Use |
|---|---|---|---|
| The Odds API | timestamped 1X2 snapshots from 2020-06-06 (10 min, 5 min from Sep 2022), EPL and BL, incl. Tipico and Winamax | historical on paid plans: $30 / $59 / $119 a month | true `T-24h` odds; live odds for paper trading |
| Betfair historical data | exchange prices from Apr 2015 | tiers unknown | sharp prices before 2020 |
| Pinnacle API | closed to the public since 23/07/2025 | n/a | none |
| OddsPortal | odds history | free | none: terms forbid scraping |
| football-data.org | fixtures and results; odds add-on | free; €15/mo odds | live fixtures |
| Understat | xG and shots from 2014/15 | free | used from Phase 4, see below |
| StatsBomb open data | event data for a few seasons and tournaments | free, credit required | Phase 4 |
| eloratings.net, martj42/international_results | national teams | free (results CC0) | EURO 2028 |

## Understat (xG, 2014/15 onward)

Files: `https://understat.com/getLeagueData/<EPL|Bundesliga>/<start year>`, JSON with every match of a season (`xG.h`, `xG.a`, `goals`, `isResult`, `datetime`, team titles), sent gzipped; the server answers 404 without the header `X-Requested-With: XMLHttpRequest`. 2014 to 2026 exist. `scripts/download_understat.py` stores each file unzipped in `data/raw/understat/<league>/<year>.json`, appends to `_manifest.jsonl` and rewrites the committed record `dbt/seeds/understat_files.csv` (test `understat_files_match_recorded_version`, warns).

### Terms: robots.txt forbids scripts (checked); downloaded anyway

> "User-agent: * / Disallow: /"

Source: <https://understat.com/robots.txt> (two lines, joined here; `Last-Modified` 13 Jul 2020), archived <https://web.archive.org/web/20260928162956/https://understat.com/robots.txt>.

The site has no terms, privacy or FAQ page: `/terms`, `/tos`, `/terms-of-use`, `/terms-and-conditions`, `/legal`, `/privacy`, `/privacy-policy`, `/faq`, `/about`, `/contact` and `/disclaimer` all return 404, and the home page links only to the league pages and `support@understat.com` (home page archived <https://web.archive.org/web/20260928163005/https://understat.com/>). So robots.txt is the only rule the site states, and it asks every script to stay off the whole site.

The project owner decided on 2026-09-28 to download regardless, for private, non-commercial research. The script goes against robots.txt; it makes 26 requests (one per league and season) at one a second, and the data is not published or passed on. Before any other use, ask Understat (`support@understat.com`).

### Team names and matching (tested)

`dbt/seeds/understat_team_names.csv` maps each Understat name to Football-Data's (24 of 67 differ, e.g. `RasenBallsport Leipzig` to `RB Leipzig`). `stg_understat__matches` joins on league, season and both teams; a pair meets once per season at each ground. Tests:

- `understat_teams_all_mapped`: every E0 and D1 team from 2014/15 has an Understat name
- `understat_matches_football_data`: every Football-Data match from 2014/15 has exactly one played Understat match with the same score, and every played Understat match has a Football-Data match (the running season excepted). All 8,318 match; one score differs by design: D1 Union Berlin v Bochum, 14/12/2024, 1-1 on Understat, the awarded 0-2 in Football-Data.

xG counts as known with the result (`result_at`). How Understat computes xG, and whether it revises old values: not checked (**unverified**).

### FBref (not used)

> "[you may not] without our express written permission, use any automated means to access or use the Site, including scripts, bots, scrapers, data miners, or similar software, in a manner that adversely impacts site performance or access"

> "[you may not] copy or use any material or Content from the Site, including without limitation any statistics, data, text, graphics, or images, for purposes of training, fine-tuning, prompting, or instructing artificial intelligence models or technologies in any manner, including without limitation for purposes of [...] (ii) supporting machine learning methods used to predict, classify, label, or score inputs into the models"

Source: <https://www.sports-reference.com/termsofuse.html> (FBref's owner, "Last Updated: May 19, 2023"), archived <https://web.archive.org/web/20260812025756/https://www.sports-reference.com/termsofuse.html>. The second clause covers a forecasting model fitted on their data, however it is fetched. Rate limit, for the record: "we will block users sending requests to: FBref and Stathead sites more often than ten requests in a minute" (<https://www.sports-reference.com/bot-traffic.html>, archived <https://web.archive.org/web/20260928163442/https://www.sports-reference.com/bot-traffic.html>).

## International football (for docs/tournament-spec.md)

Checked on 2026-09-28, before the tournament spec was frozen; the data was stored the same day, after the freeze.

Holdout: the checks below looked only at matches up to 2024-07-14. Tests that also cover later matches show those only as a count (`macros/holdout_silent.sql`), so no WC 2026 result is printed.

### martj42/international_results: licence and score rules (checked)

Licence: CC0 1.0 Universal, read in the repo's `LICENSE` file (<https://github.com/martj42/international_results/blob/master/LICENSE>, archived <https://web.archive.org/web/20260928180441/https://github.com/martj42/international_results/blob/master/LICENSE>).

> "`home_score` - full-time home team score including extra time, not including penalty-shootouts"

> "For home and away teams the *current* name of the team has been used."

Source: the repo's README (<https://github.com/martj42/international_results/blob/master/README.md>, archived <https://web.archive.org/web/20260928180505/https://github.com/martj42/international_results/blob/master/README.md>). Files: `results.csv`, `goalscorers.csv`, `shootouts.csv`, `former_names.csv`. The header of `goalscorers.csv` has a `minute` column (`date,home_team,away_team,team,scorer,minute,own_goal,penalty`), so 90-minute scores can be derived. How it records stoppage time and whether every finals goal is listed: see below.

### martj42: download (tested)

`scripts/download_international_results.py` fetches the four CSVs from `https://raw.githubusercontent.com/martj42/international_results/<commit>/<file>` at commit `394fe81893b062fbc2cf6257e988ac7cc4c039a1` (master on 2026-09-28, committed 2026-08-26; tree archived <https://web.archive.org/web/20260928183245/https://github.com/martj42/international_results/tree/394fe81893b062fbc2cf6257e988ac7cc4c039a1>). The files come UTF-8 with Unix line endings (stored bytes equal the bytes received). `dbt/seeds/international_results_files.csv` records them; test `international_results_files_match_recorded_version` (warns).

`stg_international_results__matches.match_id` is date, home team and away team: before 2011 a home team played twice on one day 31 times (last: Chile v Northern Ireland and Chile v Israel, 2010-05-30), and Tahiti met New Caledonia twice on 1974-02-17, so the second of those gets `_2`.

### martj42: stoppage time and the 90-minute score (checked, tested)

`goalscorers.csv` gives minutes as whole numbers, or `NA` (254 goals, all before 1998). Stoppage time is folded into minute 45 or 90; extra time runs 91 to 120. Checked against two matches:

| Match | Goals (Wikipedia) | `minute` in the file |
|---|---|---|
| Brazil v Costa Rica, WC 2018-06-22 | Coutinho 90+1, Neymar 90+7 | 90, 90 |
| England v Slovakia, EURO 2024-06-30 | Schranz 25; Bellingham 90+5; Kane 91 (extra time) | 25, 90, 91 |

Sources: <https://en.wikipedia.org/wiki/2018_FIFA_World_Cup_Group_E> ("Coutinho {{goal|90+1}}", "Neymar {{goal|90+7}}"), archived <https://web.archive.org/web/20260928183155/https://en.wikipedia.org/wiki/2018_FIFA_World_Cup_Group_E>; <https://en.wikipedia.org/wiki/UEFA_Euro_2024_knockout_stage> ("Bellingham {{goal|90+5}}", "Kane {{goal|91}}"), archived <https://web.archive.org/web/20260928182946/https://en.wikipedia.org/wiki/UEFA_Euro_2024_knockout_stage>. In WC and EURO finals up to EURO 2024, minute 45 holds 32 goals and 46 holds 6, minute 90 holds 111 and 91 holds 1.

So the 90-minute score counts goals at minute 90 or before (`home_score_90`, `away_score_90`). A knockout match that went to extra time comes out level at 90, whoever won it. `own_goal` rows carry the team credited with the goal: the counts match the scores below.

The rule holds in WC and EURO finals, not everywhere (see the first test below). So `score_90_reliable` is true, and the 90-minute score filled, only when:

- `goals_complete`: every goal is listed, each with a minute
- the match is not awarded (`awarded`, from `dbt/seeds/international_awarded_matches.csv`)
- outside finals, no goal is listed after minute 90 (`after_90` = 0). In finals, goals after 90 are extra time and the score stays

Outside finals, 2006-01-01 to 2024-07-14: of 11,198 competitive matches, 6,944 have every goal listed and 43 of those have a goal after minute 90, so 6,901 keep a 90-minute score. Of 6,007 friendlies, 598 have every goal listed, none with a goal after 90. Every finals match from 2006 keeps its 90-minute score, holdout included (count only).

Tests:

- `goals_after_90_only_in_level_matches`: in finals from 2006, a match with a goal after minute 90 is level at 90 (22 such matches to EURO 2024). The rule does not hold everywhere: 2003 to 2005 World Cup qualifiers put some stoppage goals at 91 to 95 (Northern Ireland v Austria, 2004-10-13, a goal at 93 with the match 2-3 at the time), and second legs such as France v Republic of Ireland, 2009-11-18, went to extra time while not level at 90. So outside finals a match with a goal after 90 gets no 90-minute score
- `score_90_only_where_reliable`: the 90-minute score is filled exactly where `score_90_reliable` is true, and that follows the rule above
- `finals_goals_listed` (warns): every finals goal from 2006 is listed with a minute. It passes: all 535 development and validation matches, and the holdout (count only). Outside finals, 2006-01-01 to 2024-07-14: 6,944 of 11,198 competitive matches and 598 of 6,007 friendlies are complete
- `score_90_within_full_score`: no team has more goals at 90 minutes than at the end
- `finals_match_counts`: WC 2006 to 2022 have 64 matches each, WC 2026 104, EURO 2008 and 2012 31, EURO 2016, 2020 and 2024 51. It passes. EURO 2020, played in 2021, has `edition` 2020

### eloratings.net: files and column meanings (checked, tested)

The site's page loads `scripts/ratings.js` (archived <https://web.archive.org/web/20260928182759/https://www.eloratings.net/scripts/ratings.js>), which reads a results file line by line:

> "row.date = formatDate(fields[0], fields[1], fields[2]); row.match = formatMatch(fields[3], fields[4]); row.score = fields[5] + '<br/>' + fields[6]; row.tournament = formatTournament(fields[7], fields[8] || fields[3], ...); row.changes = formatChange(fields[9]); row.ratings = fields[10] + '<br/>' + fields[11]; row.moves = fields[12] + '<br/>' + fields[13]; row.ranks = fields[14] + '<br/>' + fields[15];"

(function `pushMatchRow`, lines joined, trailing arguments cut). The same script loads `teams.tsv`, `en.teams.tsv` and `en.tournaments.tsv`. So a line of `<year>_results.tsv` (example archived <https://web.archive.org/web/20260928182802/https://www.eloratings.net/2006_results.tsv>) is:

| Field | Meaning |
|---|---|
| 0 to 2 | year, month, day; day `00` once (August 2004, Saint Martin v Sint Eustatius), date unknown |
| 3, 4 | team codes |
| 5, 6 | score, extra time included, shootout excluded (France v Italy, WC final 2006-07-09: 1 1) |
| 7 | tournament code (`en.tournaments.tsv`: `WC` World Cup, `EC` European Championship, `EQ` its qualifier, `F` friendly) |
| 8 | country played in; blank when team 1 is at home |
| 9 | rating points team 1 gained; team 2 lost as many |
| 10, 11 | ratings **after** the match |
| 12 to 15 | rank moves and ranks after the match (moves use the minus sign U+2212) |

Fields 10 and 11 are post-match: for every team and pair of its matches in a row, 2004 to 2026, the rating after the first plus the change in the second equals the rating after the second; as pre-match ratings, 58 of 1,484 steps in 2006 fit. Test: `eloratings_ratings_are_post_match` (count only). So `stg_eloratings__matches` gives pre-match ratings as post minus change for team 1 and post plus change for team 2. The ratings carry across the year files.

`en.teams.tsv` maps a code to names (first name used; archived <https://web.archive.org/web/20260928182830/https://www.eloratings.net/en.teams.tsv>). `teams.tsv` maps old codes to the current one (`YU RS`, `RM RS`, `MK NM`, `SZ SW`, `AN CW` and others; archived <https://web.archive.org/web/20260928182805/https://www.eloratings.net/teams.tsv>). The 2004 to 2026 files still use four old codes (RM Serbia and Montenegro, MK Macedonia, SZ Swaziland, AN Netherlands Antilles); staging turns them into the current code, as martj42 turns them into the current name.

`scripts/download_eloratings.py` fetches the three lookups and `<year>_results.tsv` for 2004 to 2026 (EURO 2004 in warm-up, then every scored year), one request a second. They come UTF-8 with Unix line endings (stored bytes equal the bytes received). The site rewrites its files: `2006_results.tsv` had `Last-Modified` 2026-09-27. `dbt/seeds/eloratings_files.csv` records them; test `eloratings_files_match_recorded_version` (warns).

The files stored on 2026-09-28 are the data version: every check here and every score rests on them. Do not download again for the backtest. A new download may change past years (ratings and matches), and the script rewrites the seed, so `git diff dbt/seeds/eloratings_files.csv` shows which years changed; then either restore the old files or commit the new record and log the change in `docs/experiment-log.md`. `data/` is not in git, so keep a copy of `data/raw/eloratings/`: the site serves only its current files.

### Team names (tested)

`dbt/seeds/team_names.csv` gives each team one `team_id`, its martj42 name and its current eloratings.net code: 236 teams, every martj42 team since 2004 that eloratings.net rates. 226 match on the first eloratings name; 10 by hand (`Czech Republic` CZ Czechia, `Republic of Ireland` IE Ireland, `American Samoa` AS Eastern Samoa, `Macau` MO Macao, `Réunion` RE, `Saint Barthélemy` BL, `São Tomé and Príncipe` ST, `Timor-Leste` TL East Timor, `United States Virgin Islands` VI, `Vatican City` VA). Left out: 84 martj42 teams eloratings does not rate (Catalonia, Jersey, other non-FIFA sides), and 4 eloratings teams martj42 lacks (Saba, Sint Eustatius, Cocos and Christmas Islands). `odds_api_name` is empty until The Odds API data comes in.

Tests:

- `international_teams_mapped`: every WC and EURO finals match and every EURO qualifier from 2006 has both teams mapped and finds its eloratings.net match on the same date with the same team ids. All do, holdout included (count only), except Italy v Serbia, EURO 2012 qualifier, 2010-10-12: "The Italy v Serbia match was abandoned after six minutes due to rioting by Serbian fans. The UEFA Control and Disciplinary Body awarded the match as a 3–0 forfeit win to Italy." (<https://en.wikipedia.org/wiki/UEFA_Euro_2012_qualifying_Group_C>, archived <https://web.archive.org/web/20260928183022/https://en.wikipedia.org/wiki/UEFA_Euro_2012_qualifying_Group_C>). martj42 has it at 3-0 with no goals listed; eloratings.net leaves it out. It is the one row of `dbt/seeds/international_awarded_matches.csv`: `awarded` is true, so it has no 90-minute score and is never scored. Its 3-0 still stands in `home_score`; a rating model should skip it, as eloratings.net does
- `finals_scores_match_eloratings`: both sources give the same score for every finals match from 2006. They do

`int_international_matches` joins the two: martj42 matches with eloratings.net pre-match ratings and score, turned to martj42's home and away. The two sources put 74 matches (13 competitive ones from 2006 to 2024-07-14, such as Kazakhstan v Germany, 2013-03-22 in martj42 and 2013-03-23 in eloratings.net) one or two days apart. For those the join takes the nearest eloratings.net match of the same teams within two days, if no other martj42 match took it; `elo_match_date` shows the date eloratings.net gives. Which source has the right date was not checked.

From 2006-01-01 to 2024-07-14, 10,655 of 11,198 competitive matches and 5,819 of 6,007 friendlies have eloratings ratings. The 543 competitive matches without, by cause (traced 2026-09-28):

| Cause | Matches | Examples |
|---|---|---|
| a team eloratings.net does not rate | 498 | Island Games 184, CONIFA World Football Cup 99, Viva World Cup 59, CONIFA European Football Cup 49, Muratti Vase 32 (Jersey 55, Guernsey 52, Padania 43, Alderney 34 and 62 other sides) |
| both teams rated, match not in eloratings.net, 3-0 with no goals listed | 20 | Italy v Serbia 2010-10-12, Romania v Norway 2020-11-15, Sri Lanka v Macau 2019-06-11: likely awarded; only Italy v Serbia is checked |
| both teams rated, played match not in eloratings.net | 25 | ELF Cup 2006 7, Palestine International Championship 2014, Nehru Cup 2012 5, Merdeka Tournament 2007 4 |

So nearly all misses are real: the matches are not in eloratings.net, or a side is not one it rates. The joins lose none of the scored matches (test `international_teams_mapped`). One mapping gap: eloratings.net's `KD` Kurdistan is martj42's `Kurdistan` (2012 and 2013 matches), but martj42 calls the same side `Iraqi Kurdistan` at the 2012 Viva World Cup, so two matches there (against Western Sahara, 2012-06-04, and Northern Cyprus, 2012-06-09) find no rating. The seed maps one name to each code, so they stay out.

### eloratings.net (unverified terms)

Files such as `https://www.eloratings.net/World.tsv` and `https://www.eloratings.net/<year>_results.tsv` answer without a key. No terms of use found: `/robots.txt` returns 404, and the about page loads its text by script, so it was not read. Used for private research only, at one request a second (docs/tournament-spec.md). Column meanings: see above.

### The Odds API: internationals (checked)

> "Historical odds data is available from June 6th 2020, with snapshots taken at 10 minute intervals. From September 2022, historical odds snapshots are available at 5 minute intervals."

Cost: historical odds and historical event odds cost "10 per region per market"; historical events cost 1, nothing if no events. Source: <https://the-odds-api.com/liveapi/guides/v4/>, archived <https://web.archive.org/web/20260928180233/https://the-odds-api.com/liveapi/guides/v4/>. The guide says historical data is "only available on paid usage plans"; the home page lists historical odds for every plan, the free one included (<https://web.archive.org/web/20260928180421/https://the-odds-api.com/>). Assume paid.

Plans: 20K credits $30/mo, 100K $59/mo, 5M $119/mo, 15M $249/mo.

Earliest snapshots, featured markets (<https://the-odds-api.com/historical-odds-data/>, archived <https://web.archive.org/web/20260928180216/https://the-odds-api.com/historical-odds-data/>):

| Key | Title | Earliest |
|---|---|---|
| `soccer_fifa_world_cup` | FIFA World Cup | 2022-04-03 |
| `soccer_uefa_european_championship` | UEFA Euro 2024 | 2021-05-19 |
| `soccer_uefa_nations_league` | UEFA Nations League | 2022-06-11 |
| `soccer_uefa_euro_qualification` | UEFA Euro Qualification | 2023-10-12 |
| `soccer_fifa_world_cup_qualifiers_europe` | FIFA World Cup Qualifiers, Europe | 2025-03-24 |
| `soccer_conmebol_copa_america` | Copa América | 2024-04-10 |
| outrights: FIFA World Cup Winner | | 2022-03-29 |

No key for friendlies; no EURO winner outright listed. The EURO key starts on 2021-05-19, before EURO 2020 (11 June 2021), so it should hold that tournament; whether every match of EURO 2020 has odds is not checked (**unverified** until a paid key queries it).

Cost for the spec: 270 tournament matches with odds (EURO 2020 51, WC 2022 64, EURO 2024 51, WC 2026 104), two snapshots each (`pre`, `close`), regions `eu` and `uk`, market `h2h`: 270 × 2 × 2 × 10 = 10,800 credits, plus about 300 for event lists and 40 for winner odds. One month of the 20K plan ($30) covers all of it.

## Tournament formats (for the simulator, docs/tournament-spec.md)

Checked on 2026-09-28. Format data (groups, bracket templates, tie-break order, best-third
tables) lives in `src/football_forecasting/tournament_formats.yaml`, read by
`football_forecasting.tournament`. Two research agents gathered this; one covered the
World Cup, one EURO, each against the official regulations first and Wikipedia's tournament
pages second. WC 2026 and EURO 2028 are format only: no group draw is stored for either
(the 2026 draw is holdout; 2028 has not been drawn), so neither is fed through the
bracket-replay tests.

### Group compositions and hosts (checked)

The final group membership and host nation(s) of WC 2006, 2010, 2014, 2018, 2022 and EURO
2008, 2012, 2016, 2020, 2024, from Wikipedia's tournament and group-stage articles (e.g.
<https://en.wikipedia.org/wiki/2018_FIFA_World_Cup>, <https://en.wikipedia.org/wiki/UEFA_Euro_2016>,
and each edition's Group A to H/F pages), cross-checked against martj42/international_results
by the bracket-replay tests below: every computed knockout pairing must match a real match
between those two teams, so a wrong team-to-group assignment fails loudly. EURO 2020 had 11
host cities in 11 countries; of those, England, Italy, Germany, Russia, Hungary, Spain,
Netherlands, Scotland and Denmark also had a team in the tournament (`hosts` uses these 9).
WC 2026 hosts (United States, Canada, Mexico) and EURO 2028 hosts (England, Scotland, Wales,
Republic of Ireland; Northern Ireland's Belfast venue was dropped in September 2024) are
common knowledge, confirmed at <https://en.wikipedia.org/wiki/UEFA_Euro_2028> and UEFA's own
announcement <https://www.uefa.com/euro2028/news/0286-1923eef9a9a6-68c007509a1b-1000/>.

### Group-stage tie-break order (checked)

FIFA (2006 to 2022): points, goal difference, goals scored, all over every group match;
then, among teams still level, points, goal difference and goals scored again but only
counting matches between them; then fair play (disciplinary points, added for 2018 and
2022 only) and drawing of lots. Source: 2010 regulations Art. 39.5, 2014 Art. 42.5, 2022
Art. 12 (archived
<https://web.archive.org/web/20260928185851/https://digitalhub.fifa.com/m/2744a0a5e3ded185/original/FIFA-World-Cup-Qatar-2022-Regulations_EN.pdf>).

FIFA 2026 changes the order to UEFA's shape (Art. 13): head-to-head first (points, then
goal difference, then goals scored, among the tied teams), reapplied to any teams still
tied, then overall goal difference, overall goals scored, disciplinary points, then the
FIFA World Ranking; drawing of lots is dropped. Archived:
<https://web.archive.org/web/20260919152026/https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf>.

UEFA (2008 to 2028): head-to-head points, then head-to-head goal difference, then
head-to-head goals scored, reapplied to any teams still tied; then overall goal difference,
overall goals scored, then (varies a little by edition) wins, disciplinary points, UEFA's
Qualifiers ranking, and lots (Germany only, 2024). Source: EURO 2024 regulations Art. 20,
archived
<https://web.archive.org/web/20220516115052/https://documents.uefa.com/api/khub/maps/5tYSJw48iUOPsbIGOxQA4w/attachments/_dSxuIv48n81YqITx97r~g/content>.

`standings()` implements: points over every match; then, for FIFA rules, goal difference
and goals scored over every match; then one combined head-to-head step (points, goal
difference, goals scored, in that order, from the same head-to-head matches, reapplied
fresh to any teams still tied after it); then, for UEFA rules, overall goal difference and
goals scored; then one random draw standing in for every criterion after that (fair play,
wins, disciplinary points, coefficient or ranking, drawing of lots): none of these are in
martj42/international_results (no cards, no rankings), so they cannot be told apart, and
the spec calls for a random stand-in with a note (docs/tournament-spec.md, Simulator). The
head-to-head step matters: at EURO 2024, Group E finished four teams level on points, and
Romania's higher goals scored across the whole group (not just against Belgium) put it
above Belgium for 2nd place; a version that re-narrowed to just the Belgium-Romania match
before comparing goals scored would rank them the other way around, and the replay test for
that tournament catches exactly this.

Two real groups needed a tie-break not in the data at all (fair play, i.e. disciplinary
points), recorded as `GROUP_OVERRIDES` in `tests/test_tournament_replay.py`:

- WC 2018 Group H: Japan above Senegal, level on points, goal difference, goals scored and
  head-to-head (2-2); Japan had fewer yellow cards. First time a World Cup group was decided
  on fair play. <https://web.archive.org/web/20260805051942/https://en.wikipedia.org/wiki/2018_FIFA_World_Cup_Group_H>
- EURO 2024 Group C: Denmark above Slovenia, level on points, head-to-head (1-1) and overall
  goal difference and goals scored; Denmark had fewer disciplinary points.
  <https://www.uefa.com/euro2024/news/028e-1b2b61087cf5-b6b99ef482fc-1000/>

No other group, and no cross-group ranking of third-placed teams, needed fair play,
coefficient ranking or lots in the ten tournaments checked (both research agents scanned
every group of all ten).

### Knockout bracket templates (checked)

WC 32-team format (2006 to 2022), Round of 16: 1A-2B, 1C-2D, 1E-2F, 1G-2H, 1B-2A, 1D-2C,
1F-2E, 1H-2G, unchanged across all five editions; quarterfinals and semifinals fold the
winners in that order (winners of matches 1 and 2 meet, then 3 and 4, and so on). Source:
2010 regulations Art. 40 to 42, 2014 Art. 43 to 45, 2022 Art. 12.7 to 12.9, checked against every
real Round of 16 pairing 2006 to 2022.

WC 48-team format (2026 on): 12 groups, top 2 plus the 8 best third-placed teams reach a
Round of 32 (FIFA regulations Art. 12.6 to 12.11). Which third-placed team plays which group
winner depends on which 8 of the 12 groups' thirds qualify: FIFA's Annexe C lists all
C(12, 8) = 495 possible sets, each with its own assignment; the full table is in
`tournament_formats.yaml` under the `wc48` shape. Source (archived):
<https://web.archive.org/web/20260919152026/https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf>.

EURO 16-team format (2008, 2012): quarterfinals 1A-2B, 1B-2A, 1C-2D, 1D-2C in both
editions, but the semifinal pairing changed: 2008 (only two knockout-stage venues) kept
QF1/QF2's winners apart from QF3/QF4's until the final; 2012 used the usual QF1/QF3 and
QF2/QF4 split. Source: 2008 regulations Art. 7.10 (archived
<https://web.archive.org/web/20081218110457/http://www.uefa.com/newsfiles/19079.pdf>), 2012
Art. 8.10 (archived
<https://web.archive.org/web/20111026215154/https://www.uefa.com/MultimediaFiles/Download/Regulations/competitions/Regulations/91/48/36/914836_DOWNLOAD.pdf>).

EURO 24-team format (2016, 2020, 2024, 2028): top 2 plus the 4 best third-placed teams
reach a Round of 16. 2016 used its own Round of 16 schedule and its own "ranking of
third-placed teams" table (winners of A, B, C, D each meet a third); 2020, 2024 and the
2028 draft regulations share one schedule and one table (winners of B, C, E, F each meet a
third). Both tables (15 rows each, one per set of 4 qualifying groups out of A-F) are in
`tournament_formats.yaml`. Source: 2016 regulations Art. 17.02/18.03 (archived
<https://web.archive.org/web/20131219025616/http://www.uefa.com/MultimediaFiles/Download/Regulations/uefaorg/Regulations/02/03/92/81/2039281_DOWNLOAD.pdf>),
2020 Art. 21.04 (archived
<https://web.archive.org/web/20210511180320/https://documents.uefa.com/internal/api/webapp/documents/WVKcnryVkASzztwJjPBcIw/content>),
2024 (same document as the tie-break quote above); 2028's draft table matches 2024's
row for row.

### Knockout draw and hosts (spec rule)

Every computed pairing above is checked against martj42/international_results by
`tests/test_tournament_replay.py`: the real winner (shootouts.csv for a penalty
shootout) of each pairing feeds the next round, and the champion must match the real
one. All ten tournaments (WC 2006-2022, EURO 2008-2024) reproduce their real group
tables, brackets and champion. A pair that met twice (once in the group stage, once
again in the knockout stage, e.g. Spain v Italy at EURO 2012) is resolved by the later
of the two real matches.

Extra time and penalties are not modelled apart: a 90-minute draw in a knockout match
goes through with `P(H) / (P(H) + P(A))` of the model's own win chances
(docs/tournament-spec.md, Simulator); this has no effect on the replay tests, which use
real results throughout. "Home" in a group or knockout match is the team whose own
country is the real venue, else neutral (docs/tournament-spec.md); where the venue is not
known match by match (EURO 2028, four host associations, drawn some 2028), `home_of`
falls back to: a host nation of the whole tournament if exactly one of the two teams is
one, else neutral. See "Venue country per match slot" below for where the fallback still
applies and where real venues are used instead.

### Venue country per match slot (checked, tested)

Six of the seven tournaments checked here are single-host: every match, group and
knockout, was played in the host country (WC 2006, 2010, 2014, 2018, 2022; EURO 2024),
recorded as `venue` in `tournament_formats.yaml`. EURO 2028 (four hosts) has no group draw
yet, so `home_of` uses the fallback rule until the draw and the venue schedule are known
(both due after the spec is frozen). WC 2026 (three hosts) has its own venue schedule: see
below.

EURO 2020 is the exception: 11 host cities in 11 countries (9 with a team in the
tournament; Azerbaijan and Romania are not), so venue country varies match by match
(`venues.groups` and `venues.knockout` in `tournament_formats.yaml`, one entry per real
match, keyed by group/round position). Sourced from Wikipedia's "UEFA Euro 2020" article
(<https://en.wikipedia.org/wiki/UEFA_Euro_2020>, archived
<https://web.archive.org/web/20260928194405/https://en.wikipedia.org/wiki/UEFA_Euro_2020>:
the host-cities table, and the note that Dublin's matches were reassigned to Saint
Petersburg (group stage) and London (round of 16) and Bilbao's to Seville), the six "UEFA
Euro 2020 Group A" to "Group F" articles (one "Venue: [stadium], [city]" line per group
match), and "UEFA Euro 2020 knockout phase"
(<https://en.wikipedia.org/wiki/UEFA_Euro_2020_knockout_phase>, archived
<https://web.archive.org/web/20260928194446/https://en.wikipedia.org/wiki/UEFA_Euro_2020_knockout_phase>:
a venue column for every round of 16, quarterfinal, semifinal and final match).

Checked two ways: `tests/test_tournament_replay.py::test_home_of_agrees_with_martj42_neutral_flag`
compares `home_of`, fed this venue data (or the fallback where there is none), against
`int_international_matches.neutral` and `home_team_id` for every real match of all ten
WC 2006-2022/EURO 2008-2024 tournaments (530 matches); it passes with one documented
exception. Separately, `results.csv`'s own `city`/`country` columns (not otherwise used
or checked elsewhere in this document) agree with the sourced venues on 50 of the 51
EURO 2020 matches.

The one exception, in both checks: Wales v Switzerland, EURO 2020, 2021-06-12. Wikipedia
has it at Baku (neutral for both teams, part of Group A's away-from-Italy fixtures,
alongside Turkey v Wales and Switzerland v Turkey, also at Baku). martj42 has `city`
"Cardiff", `country` "Wales" (Wales's own city, not a EURO 2020 venue at all) and
`neutral` false with `home_team` Wales: an error, not a second real convention, since
Wales did not play a single tournament match at home. Recorded as
`NEUTRAL_FLAG_EXCEPTIONS` in `tests/test_tournament_replay.py`; `national_elo.py`'s own
Elo ratings still read `neutral` from martj42 directly (docs/tournament-spec.md's
model step, not the simulator), so this one match keeps a small, undetected home-advantage
error there, immaterial against 369 development finals matches.

### WC 2026 draw and venues (checked, tested)

Checked 2026-09-28, for the HOLDOUT RUN. The real group draw (5 December 2025) and the
host country of every match were entered into `tournament_formats.yaml`'s `wc2026` edition
from Wikipedia's "2026 FIFA World Cup" group articles (`2026 FIFA World Cup Group A`
through `Group L`, e.g.
<https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_A>) and FIFA's own tournament
site (<https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026>), the same
two kinds of source as every earlier tournament in this document.

Cross-checked against martj42/international_results, the same way as the ten development
and validation tournaments: clustering the 72 real group-stage matches (2026-06-11 to
2026-06-27) into round-robin groups of 4 by opponent reproduces exactly the 12 Wikipedia
groups, with the same 48 teams, no mismatch. The host country of each of the 104 real
matches (`results.csv`'s own `country` column, already joined in as
`int_international_matches.country`) matches the group and knockout venue lists now in
`tournament_formats.yaml` for every match: `home_of`, fed this venue data, agrees with
`neutral`/`home_team_id` for all 104 (folded into
`tests/test_tournament_replay.py::test_home_of_agrees_with_martj42_neutral_flag`, now
covering `wc2026` too, no exception needed).

The round-of-32 seed-to-team mapping (`knockout_seeds`, and which row of the 495-row
third-place table applies) was not typed in by hand: it falls out of running the existing
`standings()` / `bracket_slots()` / `walk()` code on the real group results, the same
"replay" the HOLDOUT RUN instructions call for as a correctness check of the format before
any scoring. It reproduces the real bracket exactly, real pairing by real pairing, and the
real champion (Spain, beating Argentina 1-0 in the final; France beat England in the
third-place match) with no fair-play override needed anywhere: every group's tie-break
resolves by points, head-to-head or goal difference alone (WC 2026 uses the UEFA-style
order, `RULESETS["wc2026"]`), unlike WC 2018 and EURO 2024's one group each. This replay
uses real WC 2026 results already in the warehouse; it checks the format data only (groups,
bracket template, venues), makes no model or scoring choice, and so is not a second look at
the holdout for docs/tournament-spec.md's Rules against fooling ourselves.

### EURO 2028 qualifying (checked)

Checked 2026-09-28, for the EURO 2028 dashboard (docs/tournament-spec.md, question 3).
Sources: UEFA's own announcements and Wikipedia's "UEFA Euro 2028 qualifying" article,
cross-checked against each other.

**The draw has not happened.** It is set for 6 December 2026 in Belfast, Northern Ireland
(the ICC), after today: "The UEFA EURO 2028 qualifying draw will be held in Belfast,
Northern Ireland, on Sunday 6 December 2026"
(<https://www.uefa.com/euro2028/news/029f-1f2ff991e87b-345fffcd69c3-1000--uefa-euro-2028-qualifying-draw-to-take-place-in-belfast/>).
So `tournament_formats.yaml`'s `euro2028` entry keeps `groups: null`, and no team-to-group
assignment exists to type in.

**Format.** 12 qualifying groups of four or five teams, all 55 UEFA members entering,
each team home and away within its group: "12 qualifying groups will be formed of four or
five teams"
(<https://www.uefa.com/euro2028/news/0299-1dcf3fef69a9-41405d004b47-1000--qualification-system-for-uefa-euro-2028-approved/>).
Qualifying is played March to November 2027 (matchdays 1 and 2 in late March, 3 and 4 in
June, 5 to 10 from September to November), with any play-offs in March 2028
(<https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying>, checked 19 September 2026 by
its own last-updated note).

**Hosts do not get an automatic finals place.** Unlike EURO 2024 and earlier, England,
Scotland, Wales and the Republic of Ireland all play in qualifying, "drawn into separate
groups" so they never meet each other there (UEFA URL above). Of the 24 finals places: the
12 group winners and the 8 best-ranked runners-up (20 teams) qualify directly; "two spots
in the final tournament will be reserved for the two best-ranked host nations who are not
qualified as group winners or best runners-up"; the remaining places go through play-offs
among teams that missed out directly, the exact play-off field size depending on how many
of the 4 hosts already qualified or took a reserved place (UEFA URL above). This project's
`euro2028.py` still flags the 4 hosts on the ratings table, since they keep this safety net,
but does not treat them as qualified.

**Not yet found.** The exact seeding/pot basis for the December 2026 draw (likely the UEFA
Nations League 2024/25 standing or the country coefficient, neither confirmed in the sources
above) and the precise size of each qualifying group (four vs. five teams per group is
known; which specific groups get five is not, since the draw has not happened).

## Open checks

- The dbt test `odds_overround_plausible` warns on 65 single-bookmaker rows outside a margin of -1% to 30% (counted 2026-09-28). Likely source errors, not traced, and left in: marking them unreliable would change the stored scores.
  - E0 and D1: 2 rows at `pre` (William Hill D1 2011/12, 73%; Interwetten D1 2019/20, 31%)
  - D2, E1, E2 before 2024/25: 17 rows over 8 bookmakers, one or two a season (11 over 30%, 6 under -1%; Stan James D2 2009/10 to 2011/12, Sportingbet E1 2009/10 and E2 2007/08, William Hill E2 2010/11 among them)
  - Betfair Exchange (`BFE`), D2, E1 and E2 from 2024/25: 31 rows (26 at `pre` with margins up to 183%, 5 at `close`); see the D2, E1 and E2 section
  - E1 and E2 2025/26 at `close`: 15 rows on 7 matches, several bookmakers each under -1%, so likely stale closing prices
