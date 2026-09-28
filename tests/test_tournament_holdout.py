from datetime import date

from football_forecasting.national_elo import NationalMatch
from football_forecasting.tournament_holdout import (
    HOLDOUT_END,
    LAST_HOLDOUT_DATE,
    criteria_report,
    should_score_holdout,
)
from football_forecasting.tournament_validation import RoundRow


def make_match(
    match_id: str,
    match_date: date,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    *,
    finals: str | None,
    edition: int | None = None,
    score_90_reliable: bool = True,
) -> NationalMatch:
    return NationalMatch(
        match_id,
        match_date,
        home,
        away,
        home_score,
        away_score,
        home_score if score_90_reliable else None,
        away_score if score_90_reliable else None,
        score_90_reliable,
        True,
        False,
        "FIFA World Cup",
        finals,
        edition,
        None,
        None,
    )


def test_holdout_window_matches_the_spec():
    """docs/tournament-spec.md, Data periods: holdout 2024-07-15 to 2026-07-19."""
    assert date(2026, 7, 19) == LAST_HOLDOUT_DATE
    assert date(2026, 7, 20) == HOLDOUT_END


def test_should_score_holdout_bounds():
    too_early = make_match("m1", date(2024, 7, 14), "A", "B", 1, 0, finals="WC", edition=2026)
    first_day = make_match("m2", date(2024, 7, 15), "A", "B", 1, 0, finals="WC", edition=2026)
    last_day = make_match("m3", date(2026, 7, 19), "A", "B", 1, 0, finals="WC", edition=2026)
    too_late = make_match("m4", date(2026, 7, 20), "A", "B", 1, 0, finals="WC", edition=2026)
    not_finals = make_match("m5", date(2025, 1, 1), "A", "B", 1, 0, finals=None)
    unreliable = make_match(
        "m6", date(2025, 1, 1), "A", "B", 1, 0, finals="WC", edition=2026, score_90_reliable=False
    )
    assert not should_score_holdout(too_early)
    assert should_score_holdout(first_day)
    assert should_score_holdout(last_day)
    assert not should_score_holdout(too_late)
    assert not should_score_holdout(not_finals)
    assert not should_score_holdout(unreliable)


def test_criteria_report_pass_and_fail():
    passing = criteria_report(
        match_diffs={
            "naive-tournament-v1": (-0.10, -0.15, -0.05),
            "eloratings-v1": (0.00, -0.01, 0.01),
        },
        round_diffs={"naive-tournament-v1": (-0.04, -0.06, -0.02)},
        slope=(1.0, 0.9, 1.1),
    )
    assert "M1" in passing and "PASS" in passing.splitlines()[0]
    for line in passing.splitlines():
        assert "FAIL" not in line

    failing = criteria_report(
        match_diffs={
            "naive-tournament-v1": (0.02, -0.05, 0.09),  # CI holds 0: fails M1
            "eloratings-v1": (0.03, 0.01, 0.05),  # upper bound above 0.02: fails M2
        },
        round_diffs={"naive-tournament-v1": (0.01, -0.02, 0.04)},  # CI holds 0: fails R1
        slope=(0.5, 0.3, 0.7),  # point below 0.7: fails R2
    )
    lines = failing.splitlines()
    assert "FAIL" in lines[0]  # M1
    assert "FAIL" in lines[1]  # M2
    assert "FAIL" in lines[2]  # R1
    assert "FAIL" in lines[3]  # R2
    assert "not run" in failing  # M3


def test_rounds_report_counts_one_tournament_singular():
    from football_forecasting.tournament_holdout import rounds_report

    rows = [
        RoundRow(m, "wc2026", team, "final", 0.5, team == "a", 10_000)
        for m in ("national-elo-v1", "naive-tournament-v1", "eloratings-v1")
        for team in ("a", "b")
    ]
    report = rounds_report(rows)
    assert "1 tournament," in report
    assert "tournaments" not in report.splitlines()[0]
