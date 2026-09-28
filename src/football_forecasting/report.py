"""Scores of stored predictions: log loss, Brier and RPS by data period.

Each model is scored on the matches every listed model predicted, so the
numbers compare like with like. Holdout and warm-up seasons are never scored.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb

from football_forecasting.data import (
    FIRST_DEVELOPMENT_SEASON,
    FIRST_HOLDOUT_SEASON,
    FIRST_VALIDATION_SEASON,
    PREDICTIONS,
    WAREHOUSE,
)

MODELS = ("naive-v1", "elo-v1", "market-consensus-v1")

SCORED = """
with p as (
    select
        p.*,
        m.season,
        case when m.season < $validation then 'development' else 'validation' end as period,
        p.horizon = 'pre' and m.pre_timing_uncertain as uncertain,
        m.result,
        case m.result when 'H' then p.p_home when 'D' then p.p_draw else p.p_away end
            as p_result,
        (p.p_home - (m.result = 'H')::int) ** 2 + (p.p_draw - (m.result = 'D')::int) ** 2
            + (p.p_away - (m.result = 'A')::int) ** 2 as brier,
        -- ranked probability score over H < D < A
        ((p.p_home - (m.result = 'H')::int) ** 2 + (p.p_away - (m.result = 'A')::int) ** 2) / 2
            as rps
    from predictions as p
    inner join wh.int_matches as m using (match_id)
    where m.season >= $development and m.season < $holdout
        and p.model_version in (select unnest($models))
),

common as (
    select match_id, horizon
    from p
    group by all
    having count(distinct model_version) = len($models)
)

select * from p semi join common using (match_id, horizon)
where ($horizon is null or horizon = $horizon)
    and ($period is null or period = $period)
    and not ($certain_only and uncertain)
"""


def connect(
    predictions: Path = PREDICTIONS, warehouse: Path = WAREHOUSE
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(predictions), read_only=True)
    con.execute(f"attach '{warehouse}' as wh (read_only)")
    return con


@dataclass(frozen=True)
class Selection:
    """Which scored predictions a view covers."""

    models: tuple[str, ...] = MODELS
    horizon: str | None = None
    period: str | None = None
    certain_only: bool = False


def query(con: duckdb.DuckDBPyConnection, sql: str, sel: Selection) -> duckdb.DuckDBPyConnection:
    """Run `sql`, which reads the scored predictions as `scored`."""
    params = {
        "development": FIRST_DEVELOPMENT_SEASON,
        "validation": FIRST_VALIDATION_SEASON,
        "holdout": FIRST_HOLDOUT_SEASON,
        "models": list(sel.models),
        "horizon": sel.horizon,
        "period": sel.period,
        "certain_only": sel.certain_only,
    }
    return con.execute(f"with scored as ({SCORED}) {sql}", params)


def by_period(con: duckdb.DuckDBPyConnection, sel: Selection) -> duckdb.DuckDBPyConnection:
    return query(
        con,
        """
        select period, horizon, model_version as model, count(*) as n,
            avg(-ln(p_result)) as log_loss, avg(brier) as brier, avg(rps) as rps
        from scored
        group by all
        order by period, horizon desc, log_loss
        """,
        sel,
    )


def by_season(con: duckdb.DuckDBPyConnection, sel: Selection) -> duckdb.DuckDBPyConnection:
    """Log loss per season, one column per model."""
    columns = ", ".join(
        f"avg(-ln(p_result)) filter (where model_version = '{m}') as \"{m}\"" for m in sel.models
    )
    return query(
        con,
        f"select season, horizon, {columns} from scored group by all order by horizon desc, season",
        sel,
    )


def calibration(
    con: duckdb.DuckDBPyConnection, sel: Selection, bins: int = 10
) -> duckdb.DuckDBPyConnection:
    """Mean forecast against observed frequency, per model, outcome and probability bin."""
    return query(
        con,
        f"""
        , outcomes as (
            select model_version as model, o.outcome, o.p, (result = o.outcome)::int as hit
            from scored, unnest([
                {{'outcome': 'H', 'p': p_home}},
                {{'outcome': 'D', 'p': p_draw}},
                {{'outcome': 'A', 'p': p_away}}
            ]) as t(o)
        )
        select model, outcome, least(floor(p * {bins}), {bins - 1}) as bin,
            count(*) as n, avg(p) as forecast, avg(hit) as observed
        from outcomes
        group by all
        order by model, outcome, bin
        """,
        sel,
    )


def table(result: duckdb.DuckDBPyConnection) -> str:
    names = [d[0] for d in result.description or []]
    lines = ["| " + " | ".join(names) + " |", "|" + "---|" * len(names)]
    for row in result.fetchall():
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report(
    predictions: Path = PREDICTIONS, models: tuple[str, ...] = MODELS, warehouse: Path = WAREHOUSE
) -> str:
    con = connect(predictions, warehouse)
    return "\n\n".join(
        [
            "## All predictions",
            table(by_period(con, Selection(models))),
            "## Without pre_timing_uncertain (pre, 20 Dec to 5 Jan)",
            table(by_period(con, Selection(models, certain_only=True))),
            "## Log loss by season",
            table(by_season(con, Selection(models))),
        ]
    )
