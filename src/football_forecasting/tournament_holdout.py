"""Holdout run for WC 2026 (docs/tournament-spec.md, HOLDOUT RUN). Run exactly once:
national-elo-v1 exactly as validated (commit e4294ad), no change to the model, the
simulator, the metrics or the bootstrap after any holdout number is seen.

Reuses, unchanged, the machinery already picked on validation:
`tournament_run.forecast` (bind a model to the simulator, 10,000 seeded runs, store) and
`tournament_validation`'s scoring functions (`real_reach`, `round_rows`, `champion_rows`,
`brier`, `clipped_log_loss`, `fit_calibration_slope`, `block_bootstrap_slope`,
`calibration_curve`, `winner_report`) and `national_elo_backtest`'s match scoring
(`run`, `save`, `scores`, `table`, `calibration`). The holdout's own code here is only:
the holdout window, `should_score_holdout`, WC 2026's extra round (round of 32, the
48-team format), and this module's own pass/fail wording for the success criteria
(the validation module's `criteria_report` says "would pass"/"would fail" since
validation does not decide anything; here it is the real verdict).

Holdout period: 2024-07-15 to 2026-07-19 (WC 2026 finals, 104 matches, 48 teams). No match
after 2026-07-19 may enter anything: `HOLDOUT_END` is the exclusive upper bound passed to
both `national_elo.load` and `national_elo_backtest.run`'s `through`.

M3 (model vs the market) needs Odds API odds, not bought for this run (docs/tournament-spec.md,
Open decisions: one purchase for validation, one for the holdout run only, spent on M1/M2/R1/R2
here): reported as not run, to be scored later on these same stored predictions, no model
change.
"""

from datetime import date, timedelta

import numpy as np

from football_forecasting.national_elo import FIRST_HOLDOUT_DATE, NationalMatch, load
from football_forecasting.national_elo_backtest import calibration, run, save, scores, table
from football_forecasting.report import bootstrap
from football_forecasting.tournament_run import MODEL_VERSIONS, forecast
from football_forecasting.tournament_validation import (
    MODELS,
    RoundRow,
    block_bootstrap_slope,
    blocks_of,
    brier,
    calibration_curve,
    champion_rows,
    clipped_log_loss,
    fit_calibration_slope,
    round_rows,
    winner_report,
)

HOLDOUT_TOURNAMENT = "wc2026"
LAST_HOLDOUT_DATE = date(2026, 7, 19)
HOLDOUT_END = LAST_HOLDOUT_DATE + timedelta(days=1)  # exclusive: load()/run()'s upper bound
HOLDOUT_EDITIONS = [(HOLDOUT_TOURNAMENT, "WC", 2026)]
# WC 2026's own round sequence (48 teams, round of 32 first): docs/tournament-spec.md's
# validation tournaments (32-team WC, 24-team EURO) have no round of 32.
ROUNDS = ("round_of_32", "round_of_16", "quarterfinal", "semifinal", "final")


def should_score_holdout(m: NationalMatch) -> bool:
    """The 104 WC 2026 finals matches, and nothing on or after `HOLDOUT_END`
    (docs/tournament-spec.md, HOLDOUT RUN: no match after 2026-07-19 may enter anything)."""
    return (
        FIRST_HOLDOUT_DATE <= m.match_date < HOLDOUT_END
        and m.finals is not None
        and m.score_90_reliable
    )


def rounds_report(rows: list[RoundRow]) -> str:
    """Same body as `tournament_validation.rounds_report` (kept separate so the validation
    module's own report text, "would pass"/informational, is never touched by the holdout
    module): Brier and clipped log loss per model, national-elo-v1 minus each benchmark with
    its bootstrap CI, and national-elo-v1's calibration curve and slope."""
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
    for b, n, forecast_p, observed in calibration_curve(p["national-elo-v1"], y["national-elo-v1"]):
        lines.append(f"bin {b}: n={n} forecast={forecast_p:.3f} observed={observed:.3f}")
    a, slope = fit_calibration_slope(p["national-elo-v1"], y["national-elo-v1"])
    lo, hi = block_bootstrap_slope(
        p["national-elo-v1"], y["national-elo-v1"], blocks["national-elo-v1"]
    )
    lines.append(f"\nslope = {slope:.3f} (95% CI {lo:.3f}, {hi:.3f}), intercept = {a:.3f}")
    return "\n".join(lines)


def criteria_report(
    match_diffs: dict[str, tuple[float, float, float]],
    round_diffs: dict[str, tuple[float, float, float]],
    slope: tuple[float, float, float],
) -> str:
    """Each success criterion, the real verdict (docs/tournament-spec.md, Success criteria):
    judged on this holdout run, not informational."""
    m1_mean, m1_lo, m1_hi = match_diffs["naive-tournament-v1"]
    m2_mean, m2_lo, m2_hi = match_diffs["eloratings-v1"]
    r1_mean, r1_lo, r1_hi = round_diffs["naive-tournament-v1"]
    slope_point, slope_lo, slope_hi = slope
    m1_ok = m1_hi < 0
    m2_ok = m2_hi < 0.02
    r1_ok = r1_hi < 0
    r2_ok = slope_lo <= 1 <= slope_hi and 0.7 <= slope_point <= 1.3
    lines = [
        f"- M1 (model log loss below naive, CI excludes 0): mean {m1_mean:+.4f}, "
        f"95% CI ({m1_lo:+.4f}, {m1_hi:+.4f}) -> {'PASS' if m1_ok else 'FAIL'}",
        f"- M2 (model minus eloratings-v1 log loss upper bound below 0.02): mean {m2_mean:+.4f}, "
        f"95% CI ({m2_lo:+.4f}, {m2_hi:+.4f}) -> {'PASS' if m2_ok else 'FAIL'}",
        f"- R1 (rounds Brier below naive, CI excludes 0): mean {r1_mean:+.4f}, "
        f"95% CI ({r1_lo:+.4f}, {r1_hi:+.4f}) -> {'PASS' if r1_ok else 'FAIL'}",
        f"- R2 (calibration slope on rounds: CI holds 1, point from 0.7 to 1.3): "
        f"slope {slope_point:.3f}, 95% CI ({slope_lo:.3f}, {slope_hi:.3f}) -> "
        f"{'PASS' if r2_ok else 'FAIL'}",
        "- M3 (model minus market log loss upper bound below 0.04): not run; to be run later "
        "on the stored holdout predictions with no model change (docs/tournament-spec.md, "
        "Open decisions: no odds bought for this run).",
    ]
    return "\n".join(lines)


def main() -> None:
    matches = load(before=HOLDOUT_END)
    by_id = {m.match_id: m for m in matches}
    preds, models = run(matches, should_score=should_score_holdout, through=HOLDOUT_END)
    holdout_predictions = [
        p
        for rows_ in preds.values()
        for p in rows_
        if by_id[p.match_id].match_date >= FIRST_HOLDOUT_DATE
    ]
    new = save(holdout_predictions, list(models.values()), f"{FIRST_HOLDOUT_DATE}..{HOLDOUT_END}")
    print(f"{len(holdout_predictions)} holdout predictions, {new} new\n")
    print("## Match, holdout (WC 2026, 104 finals matches)")
    print(table(preds, by_id, tournament_only=True))
    print("\n## Calibration, match, national-elo-v1, holdout")
    for label, b, n, forecast_p, observed in calibration(preds["national-elo-v1"], by_id):
        print(f"{label} bin {b}: n={n} forecast={forecast_p:.3f} observed={observed:.3f}")

    print("\n## Forecasting WC 2026 (10,000 runs per model)")
    for model_version in MODEL_VERSIONS:
        result, new_t = forecast(HOLDOUT_TOURNAMENT, model_version)
        print(
            f"{HOLDOUT_TOURNAMENT} / {model_version}: {len(result.reach)} teams, "
            f"{result.runs} runs, seed {result.seed}, {new_t} new predictions stored"
        )

    rows = round_rows(editions=HOLDOUT_EDITIONS, rounds=ROUNDS)
    print("\n## Rounds, holdout")
    print(rounds_report(rows))

    champ_rows = champion_rows(editions=HOLDOUT_EDITIONS)
    print("\n## Winner, holdout (reported only)")
    print(winner_report(champ_rows, editions=HOLDOUT_EDITIONS))

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

    print("\n## Success criteria, holdout (docs/tournament-spec.md)")
    print(criteria_report(match_diffs, round_diffs, (slope_point, slope_lo, slope_hi)))


if __name__ == "__main__":
    main()
