"""Backtest dashboard: runs, scores, log loss by season, calibration.

Run: mise run dashboard. Reads the stores read-only; holdout seasons never
reach it, because every view goes through report.SCORED.
"""

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from football_forecasting.report import Selection, by_period, by_season, calibration, connect

# Categorical slots in fixed order (dataviz reference palette, adjacent pairs
# validated for lines). A model keeps its slot whatever else is selected.
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]


def season_label(season: str) -> str:
    return f"20{season[:2]}/{season[2:]}"


def color(models: list[str]) -> alt.Scale:
    return alt.Scale(domain=models, range=SLOTS[: len(models)])


def lines(df: pd.DataFrame, x: str, y: str, title: str, scale: alt.Scale) -> alt.LayerChart:
    """One line per model, with a crosshair and a tooltip at the nearest x."""
    hover = alt.selection_point(fields=[x], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:N", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=False)),
        color=alt.Color(
            "model:N",
            scale=scale,
            title="Model",
            legend=alt.Legend(values=sorted(df["model"].unique())),
        ),
    )
    tooltip = [alt.Tooltip(f"{x}:N"), alt.Tooltip("model:N"), alt.Tooltip(f"{y}:Q", format=".4f")]
    return alt.layer(
        base.mark_line(strokeWidth=2),
        base.mark_point(filled=True, size=64, opacity=0).encode(tooltip=tooltip).add_params(hover),
        base.mark_point(filled=True, size=64).transform_filter(hover),
        alt.Chart(df).mark_rule(color="#8a8984").encode(x=f"{x}:N").transform_filter(hover),
    )


def main() -> None:
    st.set_page_config(page_title="Football backtest", layout="wide")
    st.title("Football backtest")
    try:
        con = connect()
    except duckdb.IOException as e:
        st.error(f"Stores busy or missing (a backtest or dbt build may be running): {e}")
        return

    runs = con.execute(
        """
        select run_id, model_version, started_at, git_sha[:7] as git_sha, git_dirty, params,
            seasons, predictions, new_predictions
        from runs order by started_at desc, model_version
        """
    ).df()
    # models in the order they first appeared, so colors never move
    models = list(runs.sort_values("started_at")["model_version"].drop_duplicates())
    scale = color(models)

    left, mid, right, last = st.columns([3, 1, 1, 1])
    chosen = left.multiselect("Models", models, default=models)
    period = mid.selectbox("Period", ["development", "validation"])
    horizon = right.selectbox("Horizon", ["pre", "close"])
    certain_only = last.toggle("Skip 20 Dec to 5 Jan", help="pre odds timing is uncertain there")
    if len(chosen) < 1:
        st.info("Pick at least one model.")
        return
    sel = Selection(tuple(chosen), horizon, period, certain_only)

    st.subheader("Scores")
    st.caption("Lower is better. Every model is scored on the matches all chosen models predicted.")
    st.dataframe(by_period(con, sel).df(), hide_index=True)

    seasons = (
        by_season(con, sel)
        .df()
        .melt(id_vars=["season", "horizon"], var_name="model", value_name="log_loss")
    )
    seasons["season"] = seasons["season"].map(season_label)
    st.subheader("Log loss by season")
    st.altair_chart(lines(seasons, "season", "log_loss", "Log loss", scale), width="stretch")

    reference = st.selectbox(
        "Gap to", chosen, index=chosen.index(next((m for m in chosen if "market" in m), chosen[0]))
    )
    ref = seasons[seasons["model"] == reference].set_index("season")["log_loss"]
    gaps = seasons[seasons["model"] != reference].copy()
    gaps["gap"] = gaps["log_loss"] - gaps["season"].map(ref)
    st.subheader(f"Log loss minus {reference}, by season")
    st.caption("Above 0: worse than the reference that season.")
    if not gaps.empty:
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8a8984").encode(y="y:Q")
        st.altair_chart(
            lines(gaps, "season", "gap", "Gap in log loss", scale) + zero, width="stretch"
        )

    st.subheader("Calibration")
    st.caption(
        "Mean forecast against how often the outcome happened, in 10 bins of forecast;"
        " bins with fewer than 30 predictions left out. On the diagonal: calibrated."
    )
    cal = calibration(con, sel).df().query("n >= 30")
    cal["outcome"] = cal["outcome"].map({"H": "Home win", "D": "Draw", "A": "Away win"})
    diagonal = (
        alt.Chart()
        .mark_rule(color="#8a8984", strokeDash=[4, 4])
        .encode(x=alt.datum(0), y=alt.datum(0), x2=alt.datum(1), y2=alt.datum(1))
    )
    points = (
        alt.Chart()
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=64), strokeWidth=2)
        .encode(
            x=alt.X("forecast:Q", title="Forecast", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("observed:Q", title="Observed", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("model:N", scale=scale, title="Model"),
            tooltip=[
                "model:N",
                alt.Tooltip("forecast:Q", format=".3f"),
                alt.Tooltip("observed:Q", format=".3f"),
                "n:Q",
            ],
        )
    )
    st.altair_chart(
        alt.layer(diagonal, points, data=cal)
        .properties(width=300, height=300)
        .facet(column=alt.Column("outcome:N", title=None, sort=["Home win", "Draw", "Away win"])),
    )

    st.subheader("Runs")
    st.dataframe(runs, hide_index=True)


main()
