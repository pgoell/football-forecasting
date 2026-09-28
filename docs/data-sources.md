# Data sources

Where the data comes from, what each fact about it rests on, and how to check it again. Every quote was fetched on 2026-09-28; the archive link is a copy of the page taken the same day, so the quote stays checkable if the page changes.

Status per fact:

- **checked**: read on the source page, quoted here
- **tested**: a dbt test checks it on every build
- **unverified**: reported by a research agent or inferred; not confirmed

## Reproduce the data

```sh
mise run data:download            # 54 CSVs into data/raw/football-data/
mise run data:download:understat  # 26 JSON files into data/raw/understat/
git diff dbt/seeds/football_data_files.csv dbt/seeds/understat_files.csv
mise run dbt:build
```

`dbt/seeds/football_data_files.csv` records the sha256 of every stored CSV that the repo was built with. After a download, the diff shows which files differ; the running season's file changes with every matchday, past seasons should not. The dbt test `data_files_match_recorded_version` warns when the files on disk do not match the record.

The download stores each file as UTF-8 with Unix line endings. D1 2000/01, D1 2001/02 and E0 2004/05 come as Windows-1252; D1 2024/25 onward and E0 2021/22 and 2024/25 onward start with a BOM. `data/raw/football-data/_manifest.jsonl` keeps the sha256 of the bytes as downloaded. Test: `team_names_decoded`.

## Football-Data

Site: <https://www.football-data.co.uk>. Files: `https://www.football-data.co.uk/mmz4281/<ssss>/<E0|D1>.csv`, `ssss` = `2526` for 2025/26.

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

### Shots and shots on target (tested)

> "HS = Home Team Shots / AS = Away Team Shots / HST = Home Team Shots on Target / AST = Away Team Shots on Target"

Source: <https://www.football-data.co.uk/notes.txt> (four lines, joined here), archived <https://web.archive.org/web/20260928135540/https://football-data.co.uk/notes.txt>. The same file does not say who counts shots or by what definition since 2002/03 (**unverified**).

Coverage in our files, counted: every E0 season from 2000/01; D1 has no shots in 2002/03 and no shots on target from 2002/03 to 2005/06. D1 Union Berlin v Bochum on 14/12/2024, an awarded result, has none. Tests: `shots_coverage` (each season has them for every match or none, gaps as listed), `shots_on_target_within_shots` (warns: 3 E0 rows from the source have more shots on target than shots).

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

## Open checks

- 2 rows with a margin over 30% (1 William Hill, 1 Interwetten): the dbt test `odds_overround_plausible` warns on them; likely source errors, not yet traced.
