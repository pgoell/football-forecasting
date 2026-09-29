"""Why is the holdout's rounds calibration slope too high (1.387, too cautious: real
outcomes more extreme than forecast)? Diagnose on DEVELOPMENT tournaments only (WC 2006 to
2018, EURO 2008 to 2016), never validation or the holdout (docs/tournament-spec.md, Rules
against fooling ourselves). Nothing here is stored: forecasts run in memory and the
predictions databases are opened read-only.

Two checks, then two candidate fixes:

- Match check: is the ordered logit's spread on tournament matches already off, using the
  stored development predictions (no rerun)?
- Rounds check: run the simulator forward on development tournaments (never done before;
  only validation and the holdout went through `tournament_run`/`simulate`), score Brier and
  calibration slope of the "v1" simulator against the real bracket.
- Fix A (score pool by rating gap): group ties need a score; v1 draws one from every earlier
  finals match with the right outcome, regardless of how close the match was. A blowout and
  a nail-biter both end "H", so the pool flattens goal differences relative to the rating
  gap. Fix: bucket the pool by |eloratings.net rating gap| too, falling back to the full
  pool where a bucket is thin.
- Fix B (knockout draw split): a 90-minute draw in a knockout match goes through
  `P(H)/(P(H)+P(A))`; as an ablation of this rule's effect, try a flat 50/50 split instead
  (shootouts may be closer to a coin flip than the pre-match favourite's edge).

Run: uv run research/round-calibration/diagnose.py
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import duckdb
import numpy as np

from football_forecasting import tournament as t
from football_forecasting import tournament_run as tr
from football_forecasting import tournament_validation as tv
from football_forecasting.data import PREDICTIONS, WAREHOUSE
from football_forecasting.national_elo import FIRST_DEVELOPMENT_DATE, FIRST_VALIDATION_DATE
from football_forecasting.national_elo import outcome as outcome_of
from football_forecasting.tournament import GroupMatch, MatchProbs, ScorePool

DEV_EDITIONS = [
    ("wc2006", "WC", 2006),
    ("wc2010", "WC", 2010),
    ("wc2014", "WC", 2014),
    ("wc2018", "WC", 2018),
    ("euro2008", "EURO", 2008),
    ("euro2012", "EURO", 2012),
    ("euro2016", "EURO", 2016),
]
MODELS = ("eloratings-v1", "national-elo-v1")
SEED = 0
RUNS = 10_000

# docs/data-sources.md: the one development group a real tie-break needs fair-play data for
# (WC 2018 Group H, Japan above Senegal), the same override tests/test_tournament_replay.py
# uses. Monkeypatched into tournament_validation's dict, which real_reach() reads by fmt.id;
# validation's own euro2024 entry is untouched.
tv.GROUP_OVERRIDES["wc2018"] = {"H": ["colombia", "japan", "senegal", "poland"]}


# ─── Match check: ordered logit spread on stored development tournament predictions ───────


def match_spread_check() -> str:
    con = duckdb.connect(str(PREDICTIONS), read_only=True)
    wh = duckdb.connect(str(WAREHOUSE), read_only=True)
    lines = ["## Match check: calibration slope of the ordered logit, development finals", ""]
    lines += ["| model | n matches | slope | 95% CI |", "|---|---|---|"]
    for model in MODELS:
        rows = con.execute(
            """
            select p.match_id, p.p_home, p.p_away
            from international_predictions as p
            where p.model_version = ?
            """,
            [model],
        ).fetchall()
        match_ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(match_ids))
        truth = {
            row[0]: (row[1], row[2])
            for row in wh.execute(
                f"""
                select match_id, home_score_90, away_score_90
                from int_international_matches
                where match_id in ({placeholders}) and finals is not null
                    and match_date >= ? and match_date < ?
                """,
                [*match_ids, FIRST_DEVELOPMENT_DATE, FIRST_VALIDATION_DATE],
            ).fetchall()
        }
        p_list, y_list, block_list = [], [], []
        for match_id, p_home, p_away in rows:
            if match_id not in truth:
                continue
            hs, as_ = truth[match_id]
            p_list += [p_home, p_away]
            y_list += [float(hs > as_), float(as_ > hs)]
            block_list += [match_id, match_id]
        p = np.array(p_list)
        y = np.array(y_list)
        blocks = np.array(block_list)
        _, slope = tv.fit_calibration_slope(p, y)
        lo, hi = tv.block_bootstrap_slope(p, y, blocks)
        lines.append(f"| {model} | {len(p_list) // 2} | {slope:.3f} | ({lo:.3f}, {hi:.3f}) |")
    con.close()
    wh.close()
    return "\n".join(lines)


# ─── Rounds check: run the v1 simulator forward on development tournaments ────────────────


@dataclass(frozen=True)
class Row:
    tournament: str
    team: str
    round: str
    p: float
    y: bool


def truth_for(format_id: str, finals: str, edition: int) -> tuple[dict, str]:
    fmt = t.load_formats()[format_id]
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        return tv.real_reach(fmt, con, finals, edition)
    finally:
        con.close()


def simulate_rows(
    model_version: str,
    make_score_pool: Callable[[tr.date], ScorePool],
    make_decide_knockout: Callable[[], Callable] | None = None,
) -> list[Row]:
    """One dev tournament at a time: bind `model_version`'s match_probs, build the score pool
    with `make_score_pool(as_of)`, run the v1 simulator (or a patched `decide_knockout` for
    Fix B), score against the real bracket. Nothing stored."""
    rows = []
    real_decide_knockout = t.decide_knockout
    try:
        if make_decide_knockout is not None:
            t.decide_knockout = make_decide_knockout()
        for format_id, finals, edition in DEV_EDITIONS:
            fmt = t.load_formats()[format_id]
            as_of = tr.first_match_date(fmt.kind, fmt.year) - tr.timedelta(days=1)
            match_probs = tr.bind_match_probs(model_version, fmt, as_of)
            pool = make_score_pool(as_of)
            result = t.simulate(fmt, match_probs, pool, runs=RUNS, seed=SEED)
            truth, _ = truth_for(format_id, finals, edition)
            rounds = t.round_sequence(len(fmt.knockout_seeds))
            for team, reach in result.reach.items():
                for round_name in rounds:
                    rows.append(Row(format_id, team, round_name, reach[round_name], truth[team][round_name]))
    finally:
        t.decide_knockout = real_decide_knockout
    return rows


def report(label: str, rows: list[Row]) -> str:
    p = np.array([r.p for r in rows])
    y = np.array([float(r.y) for r in rows])
    blocks = np.array([f"{r.team}|{r.tournament}" for r in rows])
    brier = float(np.mean((p - y) ** 2))
    _, slope = tv.fit_calibration_slope(p, y)
    lo, hi = tv.block_bootstrap_slope(p, y, blocks)
    return (
        f"| {label} | {len(rows)} | {brier:.4f} | {slope:.3f} | ({lo:.3f}, {hi:.3f}) |"
    )


# ─── Fix A: score pool bucketed by |eloratings rating gap| ────────────────────────────────

GAP_EDGES = (100.0, 250.0)  # buckets: <100, 100-250, >250 (docs/experiment-log.md quantiles)
MIN_BUCKET_POOL = 15  # fall back to the full outcome pool below this


def gap_bucket(gap: float) -> int:
    for i, edge in enumerate(GAP_EDGES):
        if gap < edge:
            return i
    return len(GAP_EDGES)


def gap_pools_before(as_of) -> tuple[ScorePool, dict[int, ScorePool]]:
    """The flat pool (v1, `tournament_run.score_pool_before`) and, per gap bucket, the same
    pool restricted to matches whose own |eloratings rating gap| falls in that bucket."""
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    rows = con.execute(
        """
        select home_score_90, away_score_90, elo_home_rating_pre, elo_away_rating_pre
        from int_international_matches
        where finals is not null and score_90_reliable and match_date < ?
        """,
        [as_of],
    ).fetchall()
    con.close()
    flat: dict[str, list[tuple[int, int]]] = {"H": [], "D": [], "A": []}
    bucketed: dict[int, dict[str, list[tuple[int, int]]]] = {
        i: {"H": [], "D": [], "A": []} for i in range(len(GAP_EDGES) + 1)
    }
    for home_goals, away_goals, eh, ea in rows:
        result = outcome_of(home_goals, away_goals)
        flat[result].append((home_goals, away_goals))
        if eh is not None and ea is not None:
            bucketed[gap_bucket(abs(eh - ea))][result].append((home_goals, away_goals))
    return flat, bucketed


def make_gap_aware_simulate_group(
    ratings: dict[str, float], flat: ScorePool, bucketed: dict[int, ScorePool]
):
    def simulate_group_gap(
        teams: Sequence[str],
        hosts,
        match_probs: MatchProbs,
        _score_pool: ScorePool,
        rng,
        venues=None,
    ) -> list[GroupMatch]:
        matches = []
        for i, (a, b) in enumerate(itertools.combinations(teams, 2)):
            venue = venues[i] if venues is not None else None
            probs = match_probs(a, b, t.home_of(a, b, hosts, venue))
            outcome = t._draw_outcome(probs, rng)
            bucket = gap_bucket(abs(ratings[a] - ratings[b]))
            pool = bucketed[bucket][outcome] if len(bucketed[bucket][outcome]) >= MIN_BUCKET_POOL else flat[outcome]
            goals_a, goals_b = pool[rng.randrange(len(pool))]
            matches.append(GroupMatch(a, b, goals_a, goals_b))
        return matches

    return simulate_group_gap


def simulate_rows_fix_a(model_version: str) -> list[Row]:
    rows = []
    real_simulate_group = t.simulate_group
    try:
        for format_id, finals, edition in DEV_EDITIONS:
            fmt = t.load_formats()[format_id]
            as_of = tr.first_match_date(fmt.kind, fmt.year) - tr.timedelta(days=1)
            match_probs = tr.bind_match_probs(model_version, fmt, as_of)
            flat, bucketed = gap_pools_before(as_of)
            ratings = tr.eloratings_ratings_for(fmt, as_of)
            t.simulate_group = make_gap_aware_simulate_group(ratings, flat, bucketed)
            result = t.simulate(fmt, match_probs, flat, runs=RUNS, seed=SEED)
            truth, _ = truth_for(format_id, finals, edition)
            rounds = t.round_sequence(len(fmt.knockout_seeds))
            for team, reach in result.reach.items():
                for round_name in rounds:
                    rows.append(Row(format_id, team, round_name, reach[round_name], truth[team][round_name]))
    finally:
        t.simulate_group = real_simulate_group
    return rows


# ─── Fix B: 50/50 knockout draw split (ablation) ───────────────────────────────────────────


def decide_knockout_5050(
    team_a: str, team_b: str, home, match_probs: MatchProbs, rng
) -> str:
    p_home, p_draw, p_away = match_probs(team_a, team_b, home)
    outcome = t._draw_outcome((p_home, p_draw, p_away), rng)
    if outcome == "H":
        return team_a
    if outcome == "A":
        return team_b
    return team_a if rng.random() < 0.5 else team_b


def main() -> None:
    print(match_spread_check())
    print()
    print("## Rounds check, development (WC 2006-2018, EURO 2008-2016), v1 simulator")
    print()
    print("| variant | n team-rounds | Brier | slope | 95% CI |")
    print("|---|---|---|---|---|")
    for model in MODELS:
        rows = simulate_rows(model, tr.score_pool_before)
        print(report(f"v1, {model}", rows))
    print()
    print("## Fix A: score pool bucketed by |eloratings rating gap|")
    print()
    print("| variant | n team-rounds | Brier | slope | 95% CI |")
    print("|---|---|---|---|---|")
    for model in MODELS:
        rows = simulate_rows_fix_a(model)
        print(report(f"fix A, {model}", rows))
    print()
    print("## Fix B: 50/50 knockout draw split (ablation of P(H)/(P(H)+P(A)))")
    print()
    print("| variant | n team-rounds | Brier | slope | 95% CI |")
    print("|---|---|---|---|---|")
    for model in MODELS:
        rows = simulate_rows(model, tr.score_pool_before, make_decide_knockout=lambda: decide_knockout_5050)
        print(report(f"fix B, {model}", rows))


if __name__ == "__main__":
    main()
