"""Choose the xG weight w of xg-dc-v1 on development seasons only.

Walks the engine over warm-up and development matches (validation and holdout
are not passed in), for w in 0 (dixon-coles-v1), 0.25, 0.5, 0.75 and 1, and
prints log loss by horizon over 2014/15 to 2018/19, the development seasons
with xG (the model predicts nothing earlier). Nothing is stored.

Run: OMP_NUM_THREADS=1 uv run research/xg-weight/choose.py (one BLAS thread
per process; without it the five processes starve each other)
"""

from concurrent.futures import ProcessPoolExecutor

import numpy as np

from football_forecasting.backtest import run
from football_forecasting.data import FIRST_VALIDATION_SEASON, load
from football_forecasting.models import XgDixonColes

WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def score(w: float) -> tuple[float, dict[str, tuple[int, float]]]:
    matches, odds = load()
    matches = [m for m in matches if m.fixture.season < FIRST_VALIDATION_SEASON]
    result = {m.fixture.match_id: "HDA".index(m.result) for m in matches}
    predictions = run([XgDixonColes(w)], matches, odds)
    out = {}
    for horizon in ("pre", "close"):
        loss = [
            -np.log((p.p_home, p.p_draw, p.p_away)[result[p.match_id]])
            for p in predictions
            if p.horizon == horizon
        ]
        out[horizon] = (len(loss), float(np.mean(loss)))
    return w, out


with ProcessPoolExecutor() as pool:
    print("| w | n pre | log loss pre | log loss close |\n|---|---|---|---|")
    for w, out in pool.map(score, WEIGHTS):
        print(f"| {w} | {out['pre'][0]:,} | {out['pre'][1]:.4f} | {out['close'][1]:.4f} |")
