"""First look at the spec's betting rule, development seasons only.

Bet the outcome with the highest EV = p * odds - 1 when EV exceeds a
threshold; bet365 pre-match odds, flat 1 unit, 5.3% of the stake as tax
(docs/experiment-spec.md, Betting rule). Baseline: back bet365's favourite
on every match. Reads stored predictions; run after `mise run backtest`.
Run: uv run research/first-betting-check/check.py
"""

import duckdb

from football_forecasting.data import PREDICTIONS, WAREHOUSE

TAX = 0.053

con = duckdb.connect(str(PREDICTIONS), read_only=True)
con.execute(f"attach '{WAREHOUSE}' as wh (read_only)")
con.execute(
    """
    create temp table bets as
    select p.model_version as model, m.result,
        [p_home * odds_home - 1, p_draw * odds_draw - 1, p_away * odds_away - 1] as evs,
        [odds_home, odds_draw, odds_away] as odds
    from predictions as p
    inner join wh.int_matches as m using (match_id)
    where p.horizon = 'pre' and m.season between '0506' and '1819'
        and p.odds_home is not null
    """
)
rows = con.execute(
    """
    with pick as (
        select model, result, odds, list_max(evs) as ev, list_position(evs, list_max(evs)) as i
        from bets
    )
    select model, t as threshold, count(*) filter (where ev > t) as bets,
        avg(case when ['H', 'D', 'A'][i] = result then odds[i] - 1 else -1 end - $tax)
            filter (where ev > t) as roi
    from pick, (values (0.0), (0.05), (0.10)) as v(t)
    group by all
    order by model, t
    """,
    {"tax": TAX},
).fetchall()
favourite = con.execute(
    """
    select count(*), avg(
        case when ['H', 'D', 'A'][list_position(odds, list_min(odds))] = result
            then list_min(odds) - 1 else -1 end - $tax)
    from bets where model = 'naive-v1'
    """,
    {"tax": TAX},
).fetchone()

print("| Rule | Bets | Return per unit |\n|---|---|---|")
if favourite:
    print(f"| back the favourite | {favourite[0]} | {favourite[1]:+.1%} |")
for model, threshold, n, roi in rows:
    print(f"| {model}, EV > {threshold:.0%} | {n} | {roi:+.1%} |")
