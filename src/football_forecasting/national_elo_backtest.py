"""Walk-forward backtest for national-elo-v1 (docs/tournament-spec.md, MODEL step).

`should_score` (development, the default) scores two sets, both restricted to 2006-01-01
to 2019-12-31:

- "tournament": the 369 WC/EURO finals matches the spec scores.
- "competitive": every non-friendly match with a reliable 90-minute score, the
  spec's wider allowance for tuning, reported apart from "tournament".

`should_score_validation` scores the 166 validation finals matches (EURO 2020, WC 2022,
EURO 2024, 2020-01-01 to 2024-07-14) once instead, no wider set: validation picks the
model, it does not tune it.

Predictions are stored immutably (prediction_id, match_id, prediction_as_of,
model_version, p_home, p_draw, p_away), the same way as the league predictions
(`backtest.save`), in their own tables since this schema has no horizon or odds.

`run` refuses matches from the holdout on (2024-07-15); a count-only query confirms
holdout size without reading a single one of its matches (docs/tournament-spec.md: never
print, query or score it). The holdout run itself happens only once, separately.
"""

import csv
import hashlib
import json
import math
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import astuple, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Protocol

import duckdb
import numpy as np

from football_forecasting.backtest import git_state
from football_forecasting.data import PREDICTIONS, WAREHOUSE
from football_forecasting.models import OUTCOMES, Probs
from football_forecasting.national_elo import (
    FIRST_DEVELOPMENT_DATE,
    FIRST_HOLDOUT_DATE,
    FIRST_VALIDATION_DATE,
    EloRatingsBenchmark,
    NaiveTournamentBenchmark,
    NationalElo,
    NationalMatch,
    load,
    outcome,
    tournament_windows,
)
from football_forecasting.report import bootstrap


class Recorded(Protocol):
    """What a run records about each model: models.py's Recorded, minus horizon."""

    @property
    def version(self) -> str: ...
    @property
    def params(self) -> dict[str, float | str]: ...


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    match_id: str
    prediction_as_of: datetime
    model_version: str
    p_home: float
    p_draw: float
    p_away: float


def should_score(m: NationalMatch) -> bool:
    """Development, a reliable 90-minute score, not a friendly: the union of
    the spec's "tournament" (finals) and "competitive" (everything else
    non-friendly) sets."""
    return (
        FIRST_DEVELOPMENT_DATE <= m.match_date < FIRST_VALIDATION_DATE
        and m.score_90_reliable
        and m.tournament != "Friendly"
    )


def should_score_validation(m: NationalMatch) -> bool:
    """Validation, finals only (docs/tournament-spec.md, Data periods: EURO 2020, WC 2022,
    EURO 2024, 166 matches). No wider "all competitive" set: validation picks the model, it
    is not for tuning, so nothing beyond what the spec scores is scored here."""
    return (
        FIRST_VALIDATION_DATE <= m.match_date < FIRST_HOLDOUT_DATE
        and m.finals is not None
        and m.score_90_reliable
    )


def _prediction(version: str, m: NationalMatch, p: Probs) -> Prediction:
    key = f"{version}|{m.match_id}"
    return Prediction(
        hashlib.sha256(key.encode()).hexdigest()[:16],
        m.match_id,
        datetime.combine(m.match_date, time.min, tzinfo=UTC),
        version,
        float(p[0]),
        float(p[1]),
        float(p[2]),
    )


def run(
    matches: list[NationalMatch],
    should_score: Callable[[NationalMatch], bool] = should_score,
    through: date = FIRST_HOLDOUT_DATE,
) -> tuple[dict[str, list[Prediction]], dict[str, Recorded]]:
    """Walk `matches` in date order, predicting every match `should_score` flags before
    observing its result (so ratings and the ordered logit stay walk-forward continuous
    whether or not a given match is itself scored). Refuses anything on or after `through`
    (default 2024-07-15, the holdout's start: docs/tournament-spec.md, never print, query or
    score it before the holdout run); `should_score` defaults to development, pass
    `should_score_validation` once validation is authorized, or `should_score_holdout` with
    `through` widened to the day after the holdout's last match (`tournament_holdout.py`),
    never further."""
    if any(m.match_date >= through for m in matches):
        raise ValueError(f"match on or after {through} passed to the backtest (holdout boundary)")
    windows = tournament_windows(matches)
    elo = NationalElo(windows)
    naive = NaiveTournamentBenchmark()
    bench = EloRatingsBenchmark(windows)
    models: dict[str, Recorded] = {elo.version: elo, naive.version: naive, bench.version: bench}
    out: dict[str, list[Prediction]] = {name: [] for name in models}
    for m in matches:
        if should_score(m):
            home = None if m.neutral else m.home_team_id
            p = elo.predict(m.home_team_id, m.away_team_id, home, m.match_date)
            if p is not None:
                out[elo.version].append(_prediction(elo.version, m, p))
            p = naive.predict(m.neutral)
            if p is not None:
                out[naive.version].append(_prediction(naive.version, m, p))
            p = bench.predict(m)
            if p is not None:
                out[bench.version].append(_prediction(bench.version, m, p))
        elo.observe(m)
        naive.observe(m)
        bench.observe(m)
    return out, models


def save(
    predictions: list[Prediction], models: Sequence[Recorded], period: str, path: Path = PREDICTIONS
) -> int:
    """Record the run and append predictions not yet stored; return how many
    were new. Same immutability rules as `backtest.save` (stored predictions
    never change; a rerun stores nothing new), in its own tables."""
    con = duckdb.connect(str(path))
    con.execute(
        """
        create table if not exists international_runs (
            run_id varchar not null,
            model_version varchar not null,
            started_at timestamptz not null,
            git_sha varchar not null,
            git_dirty boolean not null,
            params json not null,
            period varchar not null,
            predictions integer not null,
            new_predictions integer not null,
            primary key (run_id, model_version)
        )
        """
    )
    con.execute(
        """
        create table if not exists international_predictions (
            prediction_id varchar primary key,
            match_id varchar not null,
            prediction_as_of timestamptz not null,
            model_version varchar not null,
            p_home double not null,
            p_draw double not null,
            p_away double not null,
            stored_at timestamptz not null default current_timestamp,
            run_id varchar not null
        )
        """
    )
    columns = list(Prediction.__dataclass_fields__)
    # through a CSV file: binding Python lists as parameters is ~100x slower (backtest.py)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="") as f:
        csv.writer(f).writerows(astuple(p) for p in predictions)
        f.flush()
        con.execute("create temp table incoming as from international_predictions limit 0")
        con.execute(f"copy incoming ({', '.join(columns)}) from '{f.name}' (header false)")
    changed = con.execute(
        f"""
        select count(*) from incoming as i
        inner join international_predictions as p using (prediction_id)
        where ({", ".join(f"i.{c}" for c in columns)})
            is distinct from ({", ".join(f"p.{c}" for c in columns)})
        """
    ).fetchone()
    if changed and changed[0]:
        raise ValueError(f"{changed[0]} stored predictions would change; bump the model version")
    run_id = uuid.uuid4().hex[:12]
    sha, dirty = git_state()
    con.execute("begin")
    con.execute(
        f"""
        insert into international_predictions ({", ".join(columns)}, run_id)
        select {", ".join(columns)}, $run_id from incoming
        where prediction_id not in (select prediction_id from international_predictions)
        """,
        {"run_id": run_id},
    )
    for model in models:
        con.execute(
            """
            insert into international_runs
            select $run_id, $version, current_timestamp, $sha, $dirty, $params, $period,
                count(*), count(*) filter (where p.run_id = $run_id)
            from incoming as i
            inner join international_predictions as p using (prediction_id)
            where i.model_version = $version
            """,
            {
                "run_id": run_id,
                "version": model.version,
                "sha": sha,
                "dirty": dirty,
                "params": json.dumps(model.params),
                "period": period,
            },
        )
    new = con.execute(
        "select count(*) from international_predictions where run_id = $run_id", {"run_id": run_id}
    ).fetchone()
    con.execute("commit")
    con.close()
    return new[0] if new else 0


def _log_loss(p: Probs, result: str) -> float:
    return -math.log(max(p[OUTCOMES.index(result)], 1e-12))


def _rps(p: Probs, result: str) -> float:
    return ((p[0] - (result == "H")) ** 2 + (p[2] - (result == "A")) ** 2) / 2


def _result_90(m: NationalMatch) -> str:
    """The 90-minute H/D/A; only called where should_score(m) already checked
    score_90_reliable, so home_score_90/away_score_90 are never null here."""
    assert m.home_score_90 is not None and m.away_score_90 is not None
    return outcome(m.home_score_90, m.away_score_90)


def scores(
    preds: dict[str, list[Prediction]], by_id: dict[str, NationalMatch], tournament_only: bool
) -> tuple[list[str], np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """match_ids all three models predicted (finals only if `tournament_only`),
    their match_date (for the bootstrap's match-day blocks) and, per model, its
    log loss and RPS on each one."""
    lookup = {
        name: {p.match_id: (p.p_home, p.p_draw, p.p_away) for p in rows}
        for name, rows in preds.items()
    }
    ids = set.intersection(*(set(v) for v in lookup.values()))
    if tournament_only:
        ids = {i for i in ids if by_id[i].finals is not None}
    ordered = sorted(ids, key=lambda i: (by_id[i].match_date, i))
    result = {i: _result_90(by_id[i]) for i in ordered}
    days = np.array([by_id[i].match_date.toordinal() for i in ordered])
    out = {}
    for name, probs in lookup.items():
        ll = np.array([_log_loss(probs[i], result[i]) for i in ordered])
        rps = np.array([_rps(probs[i], result[i]) for i in ordered])
        out[name] = (ll, rps)
    return ordered, days, out


def calibration(
    preds: list[Prediction], by_id: dict[str, NationalMatch], bins: int = 5
) -> list[tuple[str, int, int, float, float]]:
    """Mean forecast against observed frequency, per outcome and probability bin."""
    totals: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for p in preds:
        m = by_id.get(p.match_id)
        if m is None:
            continue
        result = _result_90(m)
        for label, prob in zip(OUTCOMES, (p.p_home, p.p_draw, p.p_away), strict=True):
            row = totals[label, min(int(prob * bins), bins - 1)]
            row[0] += 1
            row[1] += prob
            row[2] += float(label == result)
    return sorted(
        (label, b, int(n), fs / n, hs / n) for (label, b), (n, fs, hs) in totals.items() if n
    )


def table(
    preds: dict[str, list[Prediction]], by_id: dict[str, NationalMatch], tournament_only: bool
) -> str:
    ids, days, sc = scores(preds, by_id, tournament_only)
    names = list(preds)
    lines = [
        f"n = {len(ids)}",
        "| model | log loss | RPS |",
        "|---|---|---|",
    ]
    for name in names:
        ll, rps = sc[name]
        lines.append(f"| {name} | {ll.mean():.4f} | {rps.mean():.4f} |")
    lines += ["", "| model minus | log loss | 95% CI |", "|---|---|---|"]
    model_ll = sc["national-elo-v1"][0]
    for ref in ("naive-tournament-v1", "eloratings-v1"):
        diff = model_ll - sc[ref][0]
        lo, hi = bootstrap(diff, days, draws=10000)
        lines.append(f"| {ref} | {diff.mean():+.4f} | ({lo:+.4f}, {hi:+.4f}) |")
    return "\n".join(lines)


def confirm_counts(warehouse: Path = WAREHOUSE) -> str:
    """Counts only, no row ever read: validation and holdout are not touched."""
    con = duckdb.connect(str(warehouse), read_only=True)
    row = con.execute(
        """
        select
            count(*) filter (where finals is not null and match_date >= ? and match_date < ?),
            count(*) filter (where finals is not null and match_date >= ?)
        from int_international_matches
        """,
        [FIRST_VALIDATION_DATE, FIRST_HOLDOUT_DATE, FIRST_HOLDOUT_DATE],
    ).fetchone()
    con.close()
    validation, holdout = row if row else (0, 0)
    return (
        f"validation finals matches: {validation} (not scored, not touched further); "
        f"holdout finals matches: {holdout} (never touched)"
    )


def main() -> None:
    matches = load()  # before=FIRST_VALIDATION_DATE by default
    by_id = {m.match_id: m for m in matches}
    preds, models = run(matches)
    all_predictions = [p for rows in preds.values() for p in rows]
    new = save(
        all_predictions, list(models.values()), f"{FIRST_DEVELOPMENT_DATE}..{FIRST_VALIDATION_DATE}"
    )
    print(f"{len(all_predictions)} predictions, {new} new\n")
    print("## Tournament matches (WC/EURO finals, development)")
    print(table(preds, by_id, tournament_only=True))
    print("\n## All competitive matches, development (reported apart, per spec)")
    print(table(preds, by_id, tournament_only=False))
    tournament_preds = [p for p in preds["national-elo-v1"] if by_id[p.match_id].finals is not None]
    print("\n## Calibration, national-elo-v1, tournament matches")
    for row in calibration(tournament_preds, by_id):
        label, b, n, forecast, observed = row
        print(f"{label} bin {b}: n={n} forecast={forecast:.3f} observed={observed:.3f}")
    print("\n## Calibration, national-elo-v1, all competitive matches")
    for row in calibration(preds["national-elo-v1"], by_id):
        label, b, n, forecast, observed = row
        print(f"{label} bin {b}: n={n} forecast={forecast:.3f} observed={observed:.3f}")
    print()
    print(confirm_counts())


if __name__ == "__main__":
    main()
