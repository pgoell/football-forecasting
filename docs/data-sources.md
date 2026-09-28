# Data sources

Where the data comes from, what each fact about it rests on, and how to check it again. Every quote was fetched on 2026-09-28; the archive link is a copy of the page taken the same day, so the quote stays checkable if the page changes.

Status per fact:

- **checked**: read on the source page, quoted here
- **tested**: a dbt test checks it on every build
- **unverified**: reported by a research agent or inferred; not confirmed

## Reproduce the data

```sh
mise run data:download   # 54 CSVs into data/raw/football-data/
git diff dbt/seeds/football_data_files.csv
mise run dbt:build
```

`dbt/seeds/football_data_files.csv` records the sha256 of every stored CSV that the repo was built with. After a download, the diff shows which files differ; the running season's file changes with every matchday, past seasons should not. The dbt test `data_files_match_recorded_version` warns when the files on disk do not match the record.

The download stores each file as UTF-8 with Unix line endings. D1 2000/01, D1 2001/02 and E0 2004/05 come as Windows-1252; D1 2024/25 onward and E0 2021/22 and 2024/25 onward start with a BOM. `data/raw/football-data/_manifest.jsonl` keeps the sha256 of the bytes as downloaded. Test: `team_names_decoded`.

## Football-Data

Site: <https://www.football-data.co.uk>. Files: `https://www.football-data.co.uk/mmz4281/<ssss>/<E0|D1>.csv`, `ssss` = `2526` for 2025/26.

### Pre-match odds collection time (checked, tested for plausibility)

> "Please note that the odds are collected for the downloadable weekend fixtures on Fridays afternoons generally not later than 17:00 British Standard Time. Odds for midweek fixtures are collected Tuesdays not later than 13:00 British Standard Time."

Source: <https://www.football-data.co.uk/matches.php>, archived <https://web.archive.org/web/20260928135512/https://football-data.co.uk/matches.php>.

`int_odds.available_at` for `pre` uses this rule: matches Friday to Monday get Friday 17:00 UK time, Tuesday to Thursday get Tuesday 13:00, capped at kickoff. With kickoff times (2019/20 onward) that gives a median lead of 22h and a maximum of 75h; one Tuesday 12:30 kickoff hits the cap. Test: `pre_odds_lead_time_plausible` (0 to 96h).

**Unverified**: whether the rule held in every season since 2000/01, holiday weeks included. See [Open checks](#open-checks).

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
| Understat | xG and shots from 2014/15 | free | Phase 4 |
| StatsBomb open data | event data for a few seasons and tournaments | free, credit required | Phase 4 |
| eloratings.net, martj42/international_results | national teams | free (results CC0) | EURO 2028 |

## Open checks

- Whether the Friday/Tuesday collection rule held in every season, holiday weeks included: under way, comparing archived copies of Football-Data's files with the final files.
- 2 rows with a margin over 30% (1 William Hill, 1 Interwetten): the dbt test `odds_overround_plausible` warns on them; likely source errors, not yet traced.
