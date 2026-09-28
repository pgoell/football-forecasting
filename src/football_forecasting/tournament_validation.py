"""Validation scoring, run ONCE (docs/tournament-spec.md, Rules against fooling ourselves:
at most three model versions on validation; this is the first, national-elo-v1 as it
stands, no tuning). Validation = EURO 2020, WC 2022, EURO 2024, 2020-01-01 to 2024-07-14
(166 finals matches). The holdout (WC 2026, from 2024-07-15) is never touched here: match
scoring goes through `national_elo.load`/`national_elo_backtest.run`, both of which refuse
anything from the holdout on, and this module never queries a WC 2026 row.

Two things are scored:

- Match: national-elo-v1 vs naive-tournament-v1 vs eloratings-v1 on the 166 finals matches
  (`national_elo_backtest`'s existing machinery, widened to validation).
- Rounds: the three models' stored tournament forecasts (`tournament_run.py`, already run
  for EURO 2020, WC 2022, EURO 2024) against the real bracket (round of 16 to the final;
  the champion is scored separately, under "winner").
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.special import logit as scipy_logit

from football_forecasting.data import PREDICTIONS, WAREHOUSE
from football_forecasting.national_elo import FIRST_HOLDOUT_DATE, FIRST_VALIDATION_DATE, load
from football_forecasting.national_elo_backtest import (
    calibration,
    run,
    save,
    scores,
    should_score_validation,
    table,
)
from football_forecasting.report import bootstrap
from football_forecasting.tournament import (
    Format,
    GroupMatch,
    bracket_slots,
    load_formats,
    round_sequence,
    standings,
    walk,
)

VALIDATION_EDITIONS = [
    ("euro2020", "EURO", 2020),
    ("wc2022", "WC", 2022),
    ("euro2024", "EURO", 2024),
]
ROUNDS = ("round_of_16", "quarterfinal", "semifinal", "final")
MODELS = ("national-elo-v1", "naive-tournament-v1", "eloratings-v1")

# Real group standings this set needs fair play (disciplinary points) to decide, which we
# have no data for (docs/data-sources.md, tests/test_tournament_replay.py's GROUP_OVERRIDES):
# EURO 2024 Group C, Denmark above Slovenia.
GROUP_OVERRIDES = {"euro2024": {"C": ["england", "denmark", "slovenia", "serbia"]}}


def real_group_matches(
    con: duckdb.DuckDBPyConnection, finals: str, edition: int, teams: tuple[str, ...]
) -> list[GroupMatch]:
    placeholders = ",".join("?" * len(teams))
    rows = con.execute(
        f"""
        select home_team_id, away_team_id, home_score_90, away_score_90
        from stg_international_results__matches
        where finals = ? and edition = ?
            and home_team_id in ({placeholders}) and away_team_id in ({placeholders})
        order by match_date
        """,
        [finals, edition, *teams, *teams],
    ).fetchall()
    matches, seen = [], set()
    for home, away, home_goals, away_goals in rows:
        pair = frozenset((home, away))
        if pair in seen:
            continue
        seen.add(pair)
        matches.append(GroupMatch(home, away, home_goals, away_goals))
    return matches


def real_decider(con: duckdb.DuckDBPyConnection, finals: str, edition: int):
    def decide(team_a: str, team_b: str) -> str:
        rows = con.execute(
            """
            select home_team_id, away_team_id, home_score, away_score,
                shootout_winner, home_team
            from stg_international_results__matches
            where finals = ? and edition = ?
                and ((home_team_id = ? and away_team_id = ?)
                    or (home_team_id = ? and away_team_id = ?))
            order by match_date desc
            """,
            [finals, edition, team_a, team_b, team_b, team_a],
        ).fetchall()
        home_id, away_id, home_goals, away_goals, shootout_winner, home_name = rows[0]
        if home_goals != away_goals:
            return home_id if home_goals > away_goals else away_id
        return home_id if shootout_winner == home_name else away_id

    return decide


def real_reach(
    fmt: Format, con: duckdb.DuckDBPyConnection, finals: str, edition: int
) -> tuple[dict[str, dict[str, bool]], str]:
    """Every team of `fmt`: which knockout round it really reached, and the real champion
    (same construction as tests/test_tournament_replay.py, real group results throughout).
    For the three validation editions, the rounds are exactly `ROUNDS`."""
    assert fmt.groups is not None
    group_matches = {
        letter: real_group_matches(con, finals, edition, teams)
        for letter, teams in fmt.groups.items()
    }
    overrides = GROUP_OVERRIDES.get(fmt.id, {})
    rng = random.Random(0)
    order = {
        letter: standings(
            teams, group_matches[letter], fmt.tiebreak, rng, override=overrides.get(letter)
        )
        for letter, teams in fmt.groups.items()
    }
    slots = bracket_slots(fmt, order, group_matches, rng)
    reached, champion = walk(fmt.knockout_seeds, slots, real_decider(con, finals, edition))
    teams = [team for group in fmt.groups.values() for team in group]
    rounds = round_sequence(len(fmt.knockout_seeds))
    truth = {team: {r: team in reached[r] for r in rounds} for team in teams}
    return truth, champion


@dataclass(frozen=True)
class RoundRow:
    model: str
    tournament: str
    team: str
    round: str
    p: float
    y: bool
    runs: int


def round_rows(
    warehouse: Path = WAREHOUSE,
    predictions: Path = PREDICTIONS,
    editions: Sequence[tuple[str, str, int]] = VALIDATION_EDITIONS,
    rounds: Sequence[str] = ROUNDS,
) -> list[RoundRow]:
    """One row per model, tournament, team and round (`rounds`, not "win": scored under
    winner instead), the model's stored forecast and the real outcome. `editions`/`rounds`
    default to validation; `tournament_holdout.py` passes WC 2026 and its extra round
    (round of 32, 48-team format), the same function and math either way."""
    formats = load_formats()
    con_wh = duckdb.connect(str(warehouse), read_only=True)
    con_pred = duckdb.connect(str(predictions), read_only=True)
    rows = []
    for format_id, finals, edition in editions:
        truth, _ = real_reach(formats[format_id], con_wh, finals, edition)
        stored = con_pred.execute(
            "select model_version, team, round, p, runs from tournament_predictions"
            " where tournament = ? and round = any(?)",
            [format_id, list(rounds)],
        ).fetchall()
        for model_version, team, round_name, p, runs in stored:
            rows.append(
                RoundRow(
                    model_version, format_id, team, round_name, p, truth[team][round_name], runs
                )
            )
    con_wh.close()
    con_pred.close()
    return rows


def champion_rows(
    warehouse: Path = WAREHOUSE,
    predictions: Path = PREDICTIONS,
    editions: Sequence[tuple[str, str, int]] = VALIDATION_EDITIONS,
) -> list[RoundRow]:
    """One row per model, tournament and team, the model's stored "win" forecast and
    whether that team was the real champion. `editions` defaults to validation;
    `tournament_holdout.py` passes WC 2026."""
    formats = load_formats()
    con_wh = duckdb.connect(str(warehouse), read_only=True)
    con_pred = duckdb.connect(str(predictions), read_only=True)
    rows = []
    for format_id, finals, edition in editions:
        _, champion = real_reach(formats[format_id], con_wh, finals, edition)
        stored = con_pred.execute(
            "select model_version, team, p, runs from tournament_predictions"
            " where tournament = ? and round = 'win'",
            [format_id],
        ).fetchall()
        for model_version, team, p, runs in stored:
            rows.append(RoundRow(model_version, format_id, team, "win", p, team == champion, runs))
    con_wh.close()
    con_pred.close()
    return rows


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def clipped_log_loss(p: np.ndarray, y: np.ndarray, runs: np.ndarray) -> float:
    """docs/tournament-spec.md, Metrics: probabilities clipped at 1 / (2 * runs)."""
    lo = 1 / (2 * runs)
    pc = np.clip(p, lo, 1 - lo)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def calibration_curve(
    p: np.ndarray, y: np.ndarray, bins: int = 5
) -> list[tuple[int, int, float, float]]:
    edges = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for b in range(bins):
        mask = edges == b
        n = int(mask.sum())
        if n:
            out.append((b, n, float(p[mask].mean()), float(y[mask].mean())))
    return out


def fit_calibration_slope(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """y ~ Bernoulli(sigmoid(a + b * logit(p))) by maximum likelihood: b = 1 is perfectly
    calibrated, b < 1 overconfident, b > 1 underconfident (docs/tournament-spec.md, R2)."""
    x = scipy_logit(np.clip(p, 1e-9, 1 - 1e-9))

    def negloglik(params: np.ndarray) -> float:
        a, b = params
        pred = np.clip(expit(a + b * x), 1e-12, 1 - 1e-12)
        return float(-(y * np.log(pred) + (1 - y) * np.log(1 - pred)).sum())

    result = minimize(negloglik, np.array([0.0, 1.0]), method="BFGS")
    return float(result.x[0]), float(result.x[1])


def block_bootstrap_slope(
    p: np.ndarray, y: np.ndarray, blocks: np.ndarray, draws: int = 10_000, level: float = 0.95
) -> tuple[float, float]:
    """Calibration slope's 95% CI, resampling whole blocks (team within tournament) and
    refitting the slope each draw."""
    ids = np.unique(blocks, return_inverse=True)[1]
    k = int(ids.max()) + 1
    rows_by_block = [np.flatnonzero(ids == i) for i in range(k)]
    rng = np.random.default_rng(0)
    slopes = np.empty(draws)
    for i in range(draws):
        chosen = rng.integers(0, k, k)
        idx = np.concatenate([rows_by_block[b] for b in chosen])
        _, slopes[i] = fit_calibration_slope(p[idx], y[idx])
    tail = 50 * (1 - level)
    lo, hi = np.percentile(slopes, [tail, 100 - tail])
    return float(lo), float(hi)


def blocks_of(rows: Sequence[RoundRow]) -> np.ndarray:
    """One block per (team, tournament): "all of one team's rounds together"
    (docs/tournament-spec.md, Confidence intervals)."""
    return np.array([f"{r.team}|{r.tournament}" for r in rows])


def rounds_report(rows: list[RoundRow]) -> str:
    """`rows` from `round_rows`: validation's 3 tournaments or (`tournament_holdout.py`)
    WC 2026 alone, same math either way."""
    n_tournaments = len({r.tournament for r in rows})
    lines = [
        f"n = {len({(r.team, r.tournament) for r in rows})} teams across {n_tournaments} "
        f"tournament{'s' if n_tournaments != 1 else ''}, {len(rows)} team-round rows"
    ]
    by_model = {m: [r for r in rows if r.model == m] for m in MODELS}
    p = {m: np.array([r.p for r in rs]) for m, rs in by_model.items()}
    y = {m: np.array([float(r.y) for r in rs]) for m, rs in by_model.items()}
    runs = {m: np.array([r.runs for r in rs]) for m, rs in by_model.items()}
    blocks = {m: blocks_of(rs) for m, rs in by_model.items()}

    lines += ["", "| model | Brier | log loss (clipped) |", "|---|---|---|"]
    for m in MODELS:
        lines.append(
            f"| {m} | {brier(p[m], y[m]):.4f} | {clipped_log_loss(p[m], y[m], runs[m]):.4f} |"
        )

    lines += ["", "| model minus | Brier | 95% CI |", "|---|---|---|"]
    model_brier = (p["national-elo-v1"] - y["national-elo-v1"]) ** 2
    for ref in ("naive-tournament-v1", "eloratings-v1"):
        ref_brier = (p[ref] - y[ref]) ** 2
        diff = model_brier - ref_brier
        lo, hi = bootstrap(diff, blocks["national-elo-v1"], draws=10_000)
        lines.append(f"| {ref} | {diff.mean():+.4f} | ({lo:+.4f}, {hi:+.4f}) |")

    lines += ["", "## Calibration, rounds, national-elo-v1"]
    for b, n, forecast, observed in calibration_curve(p["national-elo-v1"], y["national-elo-v1"]):
        lines.append(f"bin {b}: n={n} forecast={forecast:.3f} observed={observed:.3f}")
    a, slope = fit_calibration_slope(p["national-elo-v1"], y["national-elo-v1"])
    lo, hi = block_bootstrap_slope(
        p["national-elo-v1"], y["national-elo-v1"], blocks["national-elo-v1"]
    )
    lines.append(f"\nslope = {slope:.3f} (95% CI {lo:.3f}, {hi:.3f}), intercept = {a:.3f}")
    return "\n".join(lines)


def winner_report(
    rows: list[RoundRow], editions: Sequence[tuple[str, str, int]] = VALIDATION_EDITIONS
) -> str:
    lines = ["| model | tournament | champion log loss | Brier (all teams) |", "|---|---|---|---|"]
    for m in MODELS:
        for format_id, _, _ in editions:
            these = [r for r in rows if r.model == m and r.tournament == format_id]
            champ = next(r for r in these if r.y)
            ll = -np.log(max(champ.p, 1 / (2 * champ.runs)))
            b = brier(np.array([r.p for r in these]), np.array([float(r.y) for r in these]))
            lines.append(f"| {m} | {format_id} | {ll:.4f} | {b:.4f} |")
    return "\n".join(lines)


def criteria_report(
    match_diffs: dict[str, tuple[float, float, float]],
    round_diffs: dict[str, tuple[float, float, float]],
    slope: tuple[float, float, float],
) -> str:
    """Each success criterion as it would read on validation (docs/tournament-spec.md,
    Success criteria); informational only, since criteria are judged on the holdout."""
    m1_mean, m1_lo, m1_hi = match_diffs["naive-tournament-v1"]
    m2_mean, m2_lo, m2_hi = match_diffs["eloratings-v1"]
    r1_mean, r1_lo, r1_hi = round_diffs["naive-tournament-v1"]
    slope_point, slope_lo, slope_hi = slope
    r2_ok = slope_lo <= 1 <= slope_hi and 0.7 <= slope_point <= 1.3
    lines = [
        "Judged on the holdout (WC 2026); these validation readings are informational only.",
        "",
        f"- M1 (model log loss below naive, CI excludes 0): mean {m1_mean:+.4f}, "
        f"95% CI ({m1_lo:+.4f}, {m1_hi:+.4f}) -> "
        f"{'would pass' if m1_hi < 0 else 'would fail'}",
        f"- M2 (model minus eloratings-v1 log loss upper bound below 0.02): mean {m2_mean:+.4f}, "
        f"95% CI ({m2_lo:+.4f}, {m2_hi:+.4f}) -> "
        f"{'would pass' if m2_hi < 0.02 else 'would fail'}",
        f"- R1 (rounds Brier below naive, CI excludes 0): mean {r1_mean:+.4f}, "
        f"95% CI ({r1_lo:+.4f}, {r1_hi:+.4f}) -> "
        f"{'would pass' if r1_hi < 0 else 'would fail'}",
        f"- R2 (calibration slope on rounds: CI holds 1, point from 0.7 to 1.3): "
        f"slope {slope_point:.3f}, 95% CI ({slope_lo:.3f}, {slope_hi:.3f}) -> "
        f"{'would pass' if r2_ok else 'would fail'}",
        "- M3 (model minus market log loss upper bound below 0.04): not run, no odds bought "
        "(docs/tournament-spec.md, Open decisions)",
    ]
    return "\n".join(lines)


def main() -> None:
    matches = load(before=FIRST_HOLDOUT_DATE)
    preds, models = run(matches, should_score=should_score_validation)
    by_id = {m.match_id: m for m in matches}
    validation_predictions = [
        p
        for rows in preds.values()
        for p in rows
        if by_id[p.match_id].match_date >= FIRST_VALIDATION_DATE
    ]
    new = save(
        validation_predictions,
        list(models.values()),
        f"{FIRST_VALIDATION_DATE}..{FIRST_HOLDOUT_DATE}",
    )
    print(f"{len(validation_predictions)} validation predictions, {new} new\n")
    print("## Match, validation (EURO 2020, WC 2022, EURO 2024, 166 matches)")
    print(table(preds, by_id, tournament_only=True))
    print("\n## Calibration, match, national-elo-v1, validation")
    for label, b, n, forecast, observed in calibration(preds["national-elo-v1"], by_id):
        print(f"{label} bin {b}: n={n} forecast={forecast:.3f} observed={observed:.3f}")

    rows = round_rows()
    print("\n## Rounds, validation")
    print(rounds_report(rows))

    champ_rows = champion_rows()
    print("\n## Winner, validation (reported only)")
    print(winner_report(champ_rows))

    _ids, days, sc = scores(preds, by_id, tournament_only=True)
    match_diffs = {}
    for ref in ("naive-tournament-v1", "eloratings-v1"):
        diff = sc["national-elo-v1"][0] - sc[ref][0]
        lo, hi = bootstrap(diff, days, draws=10_000)
        match_diffs[ref] = (float(diff.mean()), lo, hi)

    by_model = {m: [r for r in rows if r.model == m] for m in MODELS}
    p = {m: np.array([r.p for r in rs]) for m, rs in by_model.items()}
    y = {m: np.array([float(r.y) for r in rs]) for m, rs in by_model.items()}
    blocks = blocks_of(by_model["national-elo-v1"])
    round_diffs = {}
    for ref in ("naive-tournament-v1",):
        diff = (p["national-elo-v1"] - y["national-elo-v1"]) ** 2 - (p[ref] - y[ref]) ** 2
        lo, hi = bootstrap(diff, blocks, draws=10_000)
        round_diffs[ref] = (float(diff.mean()), lo, hi)
    slope_point = fit_calibration_slope(p["national-elo-v1"], y["national-elo-v1"])[1]
    slope_lo, slope_hi = block_bootstrap_slope(p["national-elo-v1"], y["national-elo-v1"], blocks)

    print("\n## Success criteria, as they would read on validation")
    print(criteria_report(match_diffs, round_diffs, (slope_point, slope_lo, slope_hi)))


if __name__ == "__main__":
    main()
