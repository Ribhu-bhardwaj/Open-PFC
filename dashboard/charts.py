"""Read-only research charts built from the complete filtered result."""
import math

import altair as alt
import pandas as pd
import streamlit as st

MEASURE_FIELDS = ["header", "label", "unit", "row_type"]
LEVEL_NAMES = {"utility": "Utility", "state_aggregate": "State aggregate"}


def measure_options(frame):
    """Keep table, definition, unit and aggregation level separate."""
    return list(frame[MEASURE_FIELDS].drop_duplicates().itertuples(index=False, name=None))


def measure_name(measure):
    header, label, unit, level = measure
    return f"{header} / {label} ({unit}; {LEVEL_NAMES.get(level, level)})"


def prepare_chart_data(frame, measure):
    """Parse numbers on a copy; never sum rows or replace missing values by zero."""
    selected = frame.loc[(frame[MEASURE_FIELDS] == pd.Series(measure, index=MEASURE_FIELDS)).all(axis=1)].copy()
    text = selected["number"].str.strip().str.replace(",", "", regex=False)
    text = text.str.replace("−", "-", regex=False).str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    selected["value"] = pd.to_numeric(text, errors="coerce")
    valid = selected["value"].map(lambda value: pd.notna(value) and math.isfinite(value))
    omitted = int((~valid).sum())
    selected = selected.loc[valid].copy()
    selected["entity"] = selected["st"] + " | " + selected["dc"] + " (" + selected["sector"] + ")"
    selected["year_start"] = selected["yod"].str[:4].astype(int)
    selected = selected.sort_values(["entity", "yop", "year_start"], kind="stable").reset_index(drop=True)
    # Lines stay within a publication and break at missing financial years.
    gap = selected.groupby(["entity", "yop"], sort=False)["year_start"].diff().ne(1)
    selected["segment"] = gap.cumsum().astype(str)
    return selected, omitted


def build_chart(frame, kind, unit):
    """One mark per source row, with no implicit sums, means, or stacking."""
    tooltip = [alt.Tooltip(field=field, type="nominal", title=title) for field, title in (
        ("label", "Measure"), ("number", "Source number"), ("unit", "Unit"),
        ("st", "State"), ("dc", "Discomm / aggregate"), ("sector", "Category"),
        ("row_type", "Sector"), ("yod", "Data year"), ("yop", "Publication"),
        ("header", "Major Head"), ("ann", "Annexure"), ("pg", "PDF page"))]
    # Inline data avoids a global Altair row-limit setting or writing chart files.
    base = alt.Chart(alt.InlineData(values=frame.to_dict("records"))).encode(tooltip=tooltip)
    if kind == "Comparison (bars)":
        return base.mark_bar().encode(
            x=alt.X("value:Q", title=unit, scale=alt.Scale(zero=True), stack=None),
            y=alt.Y("entity:N", title="State / discomm", sort="ascending"),
            yOffset=alt.YOffset("yop:N"),
            color=alt.Color("yop:N", title="Publication"),
        ).properties(height=max(320, len(frame) * 18))
    return base.mark_line(point=True).encode(
        x=alt.X("year_start:Q", title="Data year (starting year)",
                axis=alt.Axis(format="d", tickMinStep=1), scale=alt.Scale(zero=False)),
        y=alt.Y("value:Q", title=unit, scale=alt.Scale(zero=True)),
        color=alt.Color("entity:N", title="State / discomm"),
        strokeDash=alt.StrokeDash("yop:N", title="Publication"),
        detail=alt.Detail("segment:N"),
        order=alt.Order("year_start:Q"),
    ).properties(height=480).interactive()


def _choice(label, options, key, **kwargs):
    """Keep a chart selector valid when the main filters change."""
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state[key] = options[0]
    return st.selectbox(label, options, key=key, **kwargs)


def render_graphs(result):
    """Graph controls are presentation choices; they do not change the table filters."""
    measure = _choice("Graph measure", measure_options(result), "graph_measure", format_func=measure_name)
    kind = _choice("Graph type", ["Comparison (bars)", "Trend (lines)"], "graph_type")
    data, omitted = prepare_chart_data(result, measure)
    if omitted:
        st.caption(f"{omitted:,} blank or non-numeric source values cannot be plotted; the table retains them.")
    if data.empty:
        st.info("No numeric values are available for this graph measure.")
        return
    if kind == "Comparison (bars)":
        year = _choice("Graph year", sorted(data["yod"].unique(), reverse=True), "graph_year")
        data = data.loc[data["yod"] == year]
    else:
        st.caption("Lines compare years within each publication. Different publications stay separate; missing years are not connected.")
        if data["yod"].nunique() < 2:
            st.info("Select multiple data years to compare a trend. The selected year's values are shown as points.")
    st.caption(f"{len(data):,} source observations | Unit: {measure[2]} | {LEVEL_NAMES.get(measure[3], measure[3])}. Graphs use all matching rows, independent of table pagination.")
    st.altair_chart(build_chart(data, kind, measure[2]), width="stretch")
