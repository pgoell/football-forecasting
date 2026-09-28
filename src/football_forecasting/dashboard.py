"""Backtest dashboard: runs, scores, log loss by season, calibration.

Run: mise run dashboard. Reads the stores read-only; holdout seasons never
reach it, because every view goes through report.SCORED.
"""

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from football_forecasting.data import (
    FIRST_DEVELOPMENT_SEASON,
    FIRST_HOLDOUT_SEASON,
    FIRST_VALIDATION_SEASON,
)
from football_forecasting.report import Selection, by_period, by_season, calibration, connect

# Categorical slots in fixed order (dataviz reference palette, adjacent pairs
# validated for lines). A model keeps its slot whatever else is selected.
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]


def season_label(season: str) -> str:
    return f"20{season[:2]}/{season[2:]}"


def season_before(season: str) -> str:
    year = int(season[:2]) - 1
    return f"{year:02d}{year + 1:02d}"


def seasons_between(first: str, next_first: str) -> str:
    return f"{season_label(first)} to {season_label(season_before(next_first))}"


PERIODS = {
    "development": (
        f"Development ({seasons_between(FIRST_DEVELOPMENT_SEASON, FIRST_VALIDATION_SEASON)})"
    ),
    "validation": f"Validation ({seasons_between(FIRST_VALIDATION_SEASON, FIRST_HOLDOUT_SEASON)})",
}
PERIOD_HELP = (
    "Which seasons are scored. **Development**: free to try ideas and tune models on. "
    "**Validation**: used to pick the final model and betting rule, so look at it sparingly. "
    f"The seasons before {season_label(FIRST_DEVELOPMENT_SEASON)} only warm up the ratings, "
    f"and the holdout ({season_label(FIRST_HOLDOUT_SEASON)} onward) is locked until the "
    "final test, so neither appears here. More in the Glossary."
)
HORIZONS = {
    "pre": "Pre-match (Friday or Tuesday before)",
    "close": "Closing (at kickoff)",
}
HORIZON_HELP = (
    "When the forecast is made. **Pre-match**: when Football-Data records the odds, Friday "
    "17:00 UK time for weekend games and Tuesday 13:00 for midweek ones, about 1 to 3 days "
    "before kickoff. **Closing**: at kickoff, with the last odds before the game. Each model "
    "only sees results and odds known by then. More in the Glossary."
)
MODEL_HELP = (
    "**naive**: how often home wins, draws and away wins happened in the league in earlier "
    "seasons; the same forecast for every match. "
    "**elo**: team ratings that rise after good results and fall after bad ones, turned into "
    "home, draw and away chances. "
    "**poisson**: an attack and a defence strength per team, fitted to goals scored in "
    "the last three seasons, giving the chance of every score. "
    "**dixon-coles**: poisson with more weight on recent matches and a fix for how often "
    "low scores (0-0, 1-1) happen. "
    "**shots-dc**: dixon-coles fitted to goals and, with a quarter of the weight, shots on "
    "target, which say more about how well a team played than the few goals do. "
    "**xg-dc**: the same with expected goals (xG, from Understat) in place of shots; "
    "starts in 2014/15, so choosing it drops every earlier season. "
    "These run on E0 and D1 only. "
    "**elo-country** and **dixon-coles-country**: elo and dixon-coles for all five leagues, "
    "keeping a team's rating when it goes up or down between leagues of one country. "
    "**market-consensus**: the bookmakers' odds with their margin removed, taking the "
    "middle value across bookmakers. The bar to beat. "
    "**market-elo**, **market-dc**, **market-shots**, **market-xg**, "
    "**market-elo-country** and **market-dc-country**: the market forecast blended with "
    "one of our models, "
    "the blend fitted on earlier seasons; do our models add anything to the market? They "
    "start a season later than the rest (2006/07 pre-match, 2013/14 closing), so choosing "
    "them drops the first season from every model's scores. "
    "How each works, with its settings: Glossary."
)
LEAGUES = {
    "E0": "Premier League (E0)",
    "D1": "Bundesliga (D1)",
    "E1": "Championship (E1)",
    "E2": "League One (E2)",
    "D2": "2. Bundesliga (D2)",
}
LEAGUE_HELP = (
    "Which leagues are scored. The first experiment covers E0 and D1; the second asks "
    "whether our models beat the thinner market of D2, E1 and E2, with elo-country and "
    "dixon-coles-country. Models that run on E0 and D1 only leave no matches in the "
    "other leagues."
)
UNCERTAIN_HELP = (
    "Around Christmas and New Year the pre-match odds may have been recorded later than "
    "the usual Friday or Tuesday, so pre-match forecasts there might have seen late news. "
    "Switch on to leave those matches out and check the results hold without them. "
    "Changes nothing for closing forecasts."
)
GLOSSARY = (Path(__file__).parent / "glossary.md").read_text()


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


def glossary() -> None:
    st.markdown(GLOSSARY)


def backtest() -> None:
    st.title("Football backtest")
    st.markdown(
        "How well each model forecasts league matches in England and Germany, replayed "
        "match by match with only what was known at the time. Lower scores are better. "
        "New here? Start with the **Glossary** in the sidebar."
    )
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

    league_col, model_col = st.columns([1, 3])
    chosen_leagues = league_col.multiselect(
        "Leagues", list(LEAGUES), default=["E0", "D1"], format_func=LEAGUES.get, help=LEAGUE_HELP
    )
    chosen = model_col.multiselect("Models", models, default=models, help=MODEL_HELP)
    period_col, horizon_col, skip_col = st.columns(3, vertical_alignment="bottom")
    period = period_col.selectbox(
        "Seasons", list(PERIODS), format_func=PERIODS.get, help=PERIOD_HELP
    )
    horizon = horizon_col.selectbox(
        "Forecast made", list(HORIZONS), format_func=HORIZONS.get, help=HORIZON_HELP
    )
    certain_only = skip_col.toggle("Skip 20 Dec to 5 Jan", help=UNCERTAIN_HELP)
    if not chosen or not chosen_leagues:
        st.info("Pick at least one league and one model.")
        return
    sel = Selection(tuple(chosen), horizon, period, certain_only, tuple(chosen_leagues))
    if horizon == "close" and period == "development":
        st.info(
            "Closing odds exist only from 2012/13, and until 2018/19 only from Pinnacle, "
            "so with the market model chosen this view covers 2012/13 to 2018/19 and the "
            "market forecast is Pinnacle's alone."
        )

    st.subheader("Scores")
    st.caption(
        "Average over all matches in the chosen seasons. Lower is better; "
        "guessing ⅓ each scores 1.099 in log loss. What each score means: Glossary."
    )
    scores = by_period(con, sel).df()
    if scores.empty:
        st.info(
            "No match was forecast by every chosen model in these leagues. Models that run "
            "on E0 and D1 only (elo, poisson, dixon-coles, shots-dc, xg-dc and their blends) "
            "have no forecasts for D2, E1 and E2."
        )
        return
    st.dataframe(
        scores.drop(columns=["period", "horizon"]),
        hide_index=True,
        column_config={
            "model": st.column_config.TextColumn("Model"),
            "n": st.column_config.NumberColumn("Matches", help="Matches scored"),
            "log_loss": st.column_config.NumberColumn(
                "Log loss",
                help="Main score. Minus the log of the chance given to the actual result. "
                "Perfect 0, guessing ⅓ each 1.099.",
                format="%.4f",
            ),
            "brier": st.column_config.NumberColumn(
                "Brier",
                help="Squared error of the three chances. Perfect 0, guessing ⅓ each 0.667.",
                format="%.4f",
            ),
            "rps": st.column_config.NumberColumn(
                "RPS",
                help="Ranked probability score: like Brier, but a near miss (draw instead "
                "of home win) costs less than a far miss. Perfect 0, guessing ⅓ each about 0.22.",
                format="%.4f",
            ),
        },
    )

    seasons = (
        by_season(con, sel)
        .df()
        .melt(id_vars=["season", "horizon"], var_name="model", value_name="log_loss")
    )
    seasons["season"] = seasons["season"].map(season_label)
    st.subheader("Log loss by season")
    st.caption(
        "Lower is better. Seasons differ a lot in how predictable they are, so all lines "
        "move together; what matters is the order of the lines within a season."
    )
    st.altair_chart(lines(seasons, "season", "log_loss", "Log loss", scale), width="stretch")

    st.subheader("Gap to a reference model, by season")
    reference = st.selectbox(
        "Reference model",
        chosen,
        index=chosen.index(next((m for m in chosen if "market" in m), chosen[0])),
        help="Each other model's log loss minus this model's, season by season.",
    )
    ref = seasons[seasons["model"] == reference].set_index("season")["log_loss"]
    gaps = seasons[seasons["model"] != reference].copy()
    gaps["gap"] = gaps["log_loss"] - gaps["season"].map(ref)
    st.caption(
        f"Above 0: worse than {reference} that season; below 0: better. "
        "This removes the season-to-season swings of the chart above, so a model that "
        "stays below 0 season after season really beats the reference."
    )
    if not gaps.empty:
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8a8984").encode(y="y:Q")
        st.altair_chart(
            lines(gaps, "season", "gap", "Gap in log loss", scale) + zero, width="stretch"
        )

    st.subheader("Calibration")
    st.caption(
        "Do the chances mean what they say? Forecasts are grouped by chance given "
        "(0 to 10%, 10 to 20%, ...). Across: the average chance in the group; up: how often "
        "that result actually happened. On the dashed diagonal: a 40% forecast comes true "
        "40% of the time. Above it: the model was too cautious; below it: too confident. "
        "Groups with fewer than 30 forecasts are left out; hover a point for its count."
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
    st.caption(
        "Every time the backtest ran, one row per model. Forecasts are stored once and never "
        "change: a rerun that reproduces them stores nothing new, and a model whose "
        "forecasts change must get a new version name."
    )
    st.dataframe(
        runs,
        hide_index=True,
        column_config={
            "run_id": st.column_config.TextColumn("Run"),
            "model_version": st.column_config.TextColumn("Model"),
            "started_at": st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm"),
            "git_sha": st.column_config.TextColumn("Commit", help="Code version the run used"),
            "git_dirty": st.column_config.CheckboxColumn(
                "Uncommitted changes", help="The code had changes not yet committed"
            ),
            "params": st.column_config.TextColumn("Settings", help="The model's settings"),
            "seasons": st.column_config.TextColumn(
                "Data seen", help="First and last season the run read, as 0506 = 2005/06"
            ),
            "predictions": st.column_config.NumberColumn("Forecasts"),
            "new_predictions": st.column_config.NumberColumn(
                "New forecasts", help="Forecasts this run stored for the first time"
            ),
        },
    )


st.set_page_config(page_title="Football backtest", layout="wide")
st.navigation(
    [
        st.Page(backtest, title="Backtest", icon=":material/monitoring:", default=True),
        st.Page(glossary, title="Glossary", icon=":material/menu_book:"),
    ]
).run()
