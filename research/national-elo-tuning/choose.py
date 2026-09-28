"""Choose national-elo-v1's home advantage, K weights and goal-difference
multiplier on development only (docs/tournament-spec.md, MODEL step).

Walks the engine over every match before validation (`national_elo.load`'s
default), scoring log loss on the 369 WC/EURO finals matches in development
(2006-01-01 to 2019-12-31). Nothing is stored; validation is never scored.
K and G variants monkeypatch `national_elo.match_weight` /
`national_elo.goal_multiplier`, since `NationalElo.observe` calls the
module-level functions.

Run: uv run research/national-elo-tuning/choose.py
"""

import numpy as np

from football_forecasting import national_elo as ne

FIRST_DEV = ne.FIRST_DEVELOPMENT_DATE
FIRST_VAL = ne.FIRST_VALIDATION_DATE


def is_tournament_dev(m: ne.NationalMatch) -> bool:
    return FIRST_DEV <= m.match_date < FIRST_VAL and m.finals is not None and m.score_90_reliable


def is_competitive_dev(m: ne.NationalMatch) -> bool:
    return (
        FIRST_DEV <= m.match_date < FIRST_VAL and m.score_90_reliable and m.tournament != "Friendly"
    )


def score(matches: list[ne.NationalMatch], home_advantage: float) -> tuple[float, float, int, int]:
    """Log loss on the tournament (finals) set and the wider competitive set."""
    windows = ne.tournament_windows(matches)
    model = ne.NationalElo(windows, home_advantage=home_advantage)
    tournament_losses, competitive_losses = [], []
    for m in matches:
        if is_competitive_dev(m):
            home = None if m.neutral else m.home_team_id
            p = model.predict(m.home_team_id, m.away_team_id, home, m.match_date)
            if p is not None:
                assert m.home_score_90 is not None and m.away_score_90 is not None
                result = ne.outcome(m.home_score_90, m.away_score_90)
                loss = -np.log(max(p[ne.OUTCOMES.index(result)], 1e-12))
                competitive_losses.append(loss)
                if is_tournament_dev(m):
                    tournament_losses.append(loss)
        model.observe(m)
    return (
        float(np.mean(tournament_losses)),
        float(np.mean(competitive_losses)),
        len(tournament_losses),
        len(competitive_losses),
    )


def flat(weight: float):
    """Every scored-type match weighted the same: is the tiered K worth it?"""

    def k(_tournament: str) -> float:
        return weight

    return k


def no_goal_multiplier(_goal_difference: int) -> float:
    return 1.0


def main() -> None:
    matches = ne.load()
    real_k, real_g = ne.match_weight, ne.goal_multiplier
    rows: list[tuple[str, float]] = []

    print(
        "| K | home advantage | tournament n | tournament log loss | competitive n | competitive log loss |"
    )
    print("|---|---|---|---|---|---|")

    def row(label: str, home_advantage: float) -> None:
        t_loss, c_loss, t_n, c_n = score(matches, home_advantage)
        print(f"| {label} | {home_advantage:.0f} | {t_n} | {t_loss:.4f} | {c_n} | {c_loss:.4f} |")
        rows.append((f"{label}, home {home_advantage:.0f}", t_loss))

    for home_advantage in (60.0, 80.0, 100.0, 150.0):
        row("eloratings.net tiered (20/30/40/50/60)", home_advantage)

    for weight in (20.0, 30.0, 40.0, 50.0, 60.0):
        ne.match_weight = flat(weight)  # type: ignore[assignment]
        row(f"flat K = {weight:.0f}", 100.0)
    ne.match_weight = real_k

    ne.goal_multiplier = no_goal_multiplier  # type: ignore[assignment]
    row("eloratings.net tiered, G = 1 (off)", 100.0)
    ne.goal_multiplier = real_g

    best = min(rows, key=lambda r: r[1])
    print(f"\nBest tournament log loss: {best[0]} ({best[1]:.4f})")


if __name__ == "__main__":
    main()
