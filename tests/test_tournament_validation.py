from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pytest

from football_forecasting.tournament import Format
from football_forecasting.tournament_validation import (
    RoundRow,
    blocks_of,
    brier,
    calibration_curve,
    clipped_log_loss,
    fit_calibration_slope,
    real_reach,
)


def test_brier():
    p = np.array([1.0, 0.0, 0.5])
    y = np.array([1.0, 0.0, 0.0])
    assert brier(p, y) == pytest.approx((0 + 0 + 0.25) / 3)


def test_clipped_log_loss_avoids_infinity_at_the_extremes():
    p = np.array([1.0, 0.0])
    y = np.array([0.0, 0.0])  # a certain-looking forecast that was wrong both times
    runs = np.array([10_000, 10_000])
    loss = clipped_log_loss(p, y, runs)
    assert np.isfinite(loss)
    # clipped at 1/(2*10000) = 0.00005: the p=1 miss costs -log(0.00005) ~= 9.9, the p=0
    # "miss" costs ~0; mean of the two is ~4.95
    assert loss == pytest.approx(4.95, abs=0.05)


def test_calibration_curve_bins_by_predicted_probability():
    p = np.array([0.05, 0.15, 0.85, 0.95])  # 5 bins, width 0.2: the pairs land together
    y = np.array([0.0, 1.0, 1.0, 1.0])
    curve = calibration_curve(p, y, bins=5)
    bins = {b: (n, forecast, observed) for b, n, forecast, observed in curve}
    assert bins[0] == (2, pytest.approx(0.1), pytest.approx(0.5))
    assert bins[4] == (2, pytest.approx(0.9), pytest.approx(1.0))


def test_fit_calibration_slope_is_near_one_when_perfectly_calibrated():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 4000)
    y = (rng.uniform(size=4000) < p).astype(float)
    _, slope = fit_calibration_slope(p, y)
    assert slope == pytest.approx(1.0, abs=0.15)


def test_fit_calibration_slope_below_one_when_overconfident():
    # true rate is always 0.5, forecasts are overconfident (near 0 or 1): slope should be
    # well below 1 (the model overreacts to whatever it thinks it knows)
    rng = np.random.default_rng(0)
    p = np.where(rng.uniform(size=4000) < 0.5, 0.95, 0.05)
    y = (rng.uniform(size=4000) < 0.5).astype(float)
    _, slope = fit_calibration_slope(p, y)
    assert slope < 0.3


def test_blocks_of_groups_by_team_and_tournament():
    rows = [
        RoundRow("m", "euro2020", "italy", "round_of_16", 0.9, True, 10_000),
        RoundRow("m", "euro2020", "italy", "final", 0.3, False, 10_000),
        RoundRow("m", "euro2024", "italy", "round_of_16", 0.5, False, 10_000),
    ]
    blocks = blocks_of(rows)
    assert blocks[0] == blocks[1] != blocks[2]


COLUMNS = """
    match_date date, home_team_id varchar, away_team_id varchar,
    home_score integer, away_score integer, home_score_90 integer, away_score_90 integer,
    finals varchar, edition integer, home_team varchar, shootout_winner varchar
"""


def stg_warehouse(tmp_path: Path, rows: list[tuple]) -> Path:
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute(f"create table stg_international_results__matches ({COLUMNS})")
    con.executemany(
        "insert into stg_international_results__matches values (?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    con.close()
    return path


def match_row(
    d: date,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    shootout_winner: str | None = None,
) -> tuple:
    return (
        d,
        home,
        away,
        home_score,
        away_score,
        home_score,
        away_score,
        "EURO",
        2020,
        home,
        shootout_winner,
    )


def small_format() -> Format:
    return Format(
        id="test2020",
        kind="EURO",
        year=2020,
        format_version="test-v1",
        hosts=(),
        groups={"A": ("a", "b", "c", "d")},
        third_place_advance=0,
        third_place_table=None,
        knockout_seeds=(("1A", "2A"),),
        tiebreak="euro",
    )


def test_real_reach_reports_group_and_knockout_outcomes(tmp_path):
    rows = [
        # group A, round-robin: a wins the group, b is runner-up
        match_row(date(2020, 6, 1), "a", "b", 3, 0),
        match_row(date(2020, 6, 2), "c", "d", 1, 1),
        match_row(date(2020, 6, 3), "a", "c", 2, 0),
        match_row(date(2020, 6, 4), "b", "d", 1, 0),
        match_row(date(2020, 6, 5), "a", "d", 1, 0),
        match_row(date(2020, 6, 6), "b", "c", 2, 0),
        # final: a beats b
        match_row(date(2020, 6, 10), "a", "b", 1, 0),
    ]
    path = stg_warehouse(tmp_path, rows)
    con = duckdb.connect(str(path), read_only=True)
    try:
        truth, champion = real_reach(small_format(), con, "EURO", 2020)
    finally:
        con.close()
    assert champion == "a"
    assert truth["a"] == {"final": True}
    assert truth["b"] == {"final": True}
    assert truth["c"] == {"final": False}
    assert truth["d"] == {"final": False}
