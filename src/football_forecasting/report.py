"""Scores of stored predictions: log loss, Brier and RPS by data period.

Each model is scored on the matches every listed model predicted, so the
numbers compare like with like. Holdout and warm-up seasons are never scored.
"""

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
"""


def table(con: duckdb.DuckDBPyConnection, sql: str, params: dict) -> str:
    rel = con.execute(sql, params)
    names = [d[0] for d in rel.description]
    lines = ["| " + " | ".join(names) + " |", "|" + "---|" * len(names)]
    for row in rel.fetchall():
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report(
    predictions: Path = PREDICTIONS, models: tuple[str, ...] = MODELS, warehouse: Path = WAREHOUSE
) -> str:
    con = duckdb.connect(str(predictions), read_only=True)
    con.execute(f"attach '{warehouse}' as wh (read_only)")
    params = {
        "development": FIRST_DEVELOPMENT_SEASON,
        "validation": FIRST_VALIDATION_SEASON,
        "holdout": FIRST_HOLDOUT_SEASON,
        "models": list(models),
    }
    by_period = f"""
        select period, horizon, model_version as model, count(*) as n,
            avg(-ln(p_result)) as log_loss, avg(brier) as brier, avg(rps) as rps
        from ({SCORED})
        {{where}}
        group by all
        order by period, horizon desc, log_loss
    """
    by_season = f"""
        pivot (select season, horizon, model_version, -ln(p_result) as log_loss from ({SCORED}))
        on model_version in ({", ".join(f"'{m}'" for m in models)}) using avg(log_loss)
        order by horizon desc, season
    """
    return "\n\n".join(
        [
            "## All predictions",
            table(con, by_period.format(where=""), params),
            "## Without pre_timing_uncertain (pre, 20 Dec to 5 Jan)",
            table(con, by_period.format(where="where not uncertain"), params),
            "## Log loss by season",
            table(con, by_season, params),
        ]
    )
