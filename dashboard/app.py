"""Local, read-only Streamlit view of the existing flat files."""
import math
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_access import (VIEWS, LATEST_VIEW, read_catalog, read_sources, select_sources,
                         selected_report_pairs, state_names, filter_records, heading_options,
                         discomm_options, filter_discomms, label_columns)

from charts import render_graphs

st.set_page_config(page_title="PFC-Report on discomms-Dashboard", layout="wide")


@st.cache_data(show_spinner=False, max_entries=24)
def load_files(sources, signatures):
    # Signatures invalidate memory-only caching when the underlying files change.
    return read_sources(sources)


def reset_page():
    st.session_state["page"] = 1


def clear_all():
    """Clear other filters and restore Latest available as the selected view."""
    for key in ("year", "view", "sector", "row_type", "state", "major_heads", "minor_heads", "discomms"):
        st.session_state[key] = []
        st.session_state[f"{key}_options"] = []
        st.session_state[f"{key}_all_selected"] = False
    st.session_state["view"] = [LATEST_VIEW]
    reset_page()


def multiselect(container, label, options, *, key, default=None, **kwargs):
    """Keep stored choices valid and migrate the former All entry."""
    follow_all = default is None
    all_selected = False
    if key in st.session_state:
        selected = st.session_state[key]
        previous_options = st.session_state.get(f"{key}_options")
        all_selected = follow_all and (set(selected) == set(previous_options) if previous_options
                                       else st.session_state.get(f"{key}_all_selected", False))
        valid = list(options) if "All" in selected or all_selected else [
            value for value in selected if value in options]
        if valid != selected:
            st.session_state[key] = valid
        default = None
    elif default is None:
        default = options
    st.session_state[f"{key}_options"] = list(options)
    selected = container.multiselect(label, options, default=default,
                                     key=key, on_change=reset_page, select_all=True, **kwargs)
    st.session_state[f"{key}_all_selected"] = (
        follow_all and set(selected) == set(options) if options else all_selected)
    return selected


st.title("PFC-Report on discomms-Dashboard")
try:
    catalog = read_catalog()
except (OSError, ValueError, KeyError) as exc:
    st.error(f"Unable to read the flat-file index: {exc}")
    st.stop()

years = sorted({s.year for s in catalog}, reverse=True)
for key in ("year", "view", "heading", "state", "row_type", "sector"):
    if isinstance(st.session_state.get(key), str):
        st.session_state[key] = [st.session_state[key]]
first = st.columns(6)
additional = st.columns(3)
year = multiselect(first[0], "Select year", years, default=[years[0]], key="year",
                        help="The data year (yod), not the report edition.")
view = multiselect(additional[0], "Select view", [LATEST_VIEW, *VIEWS], default=[LATEST_VIEW], key="view",
                        help="Latest available: newest available report for each selected data year. Preliminary: same-year report. Revision 1: next report. Revision 2: report two years later.")
additional[2].button("Clear All", key="clear_all", on_click=clear_all)
sector = multiselect(first[1], "Category", ["Public", "Private"], key="sector")
row_type = multiselect(first[2], "Sector", ["State aggregate", "Utility"], key="row_type")
headings = heading_options(catalog, year, view)
if st.session_state.get("minor_heads_kind") != "labels" and "major_heads" in st.session_state:
    st.session_state["major_heads"] = list(dict.fromkeys(
        st.session_state["major_heads"] + [name for name in st.session_state.get("minor_heads", [])
                                          if name in headings]))
major_heads = multiselect(first[4], "Major Heads", headings, key="major_heads")
reports = list(dict.fromkeys("20" + report for report, _ in selected_report_pairs(catalog, year, view)))
st.caption(f"Data year: {', '.join(year)} | View: {', '.join(view)} | Source report: {', '.join(reports)}")

sources = select_sources(catalog, year, view, major_heads)
try:
    signatures = tuple((str(s.path), s.path.stat().st_mtime_ns, s.path.stat().st_size) for s in sources)
    data = load_files(tuple(sources), signatures)
except (OSError, ValueError, KeyError) as exc:
    st.error(f"Unable to read the selected flat files: {exc}")
    st.stop()

# Migrate the previous table-based Minor Heads once, retaining selected tables.
# Old empty selections meant all measures of the selected parent tables.
minor_options = list(dict.fromkeys(data["label"]))
if st.session_state.get("minor_heads_kind") != "labels":
    explicitly_cleared = "year" in st.session_state and not st.session_state["year"]
    st.session_state["minor_heads"] = [] if explicitly_cleared else minor_options
    st.session_state["minor_heads_options"] = list(minor_options)
    st.session_state["minor_heads_all_selected"] = not explicitly_cleared
    st.session_state["minor_heads_kind"] = "labels"
minor_heads = multiselect(first[5], "Minor Heads", minor_options, key="minor_heads",
                          help="Measures from the label column of the selected Major Heads. A shared label selects that measure in every selected table containing it.")

states = state_names(data)
state = multiselect(first[3], "State (st)", states, key="state")

category_filter = "All" if set(sector) == {"Public", "Private"} else sector
result = filter_records(data, state, row_type, category_filter)
discomms_active = "Utility" in row_type and bool(state) and bool(sector)
options = discomm_options(result) if discomms_active else []
discomms = multiselect(additional[1], "Discomms", options, key="discomms",
                      format_func=lambda item: f"{item[2]} ({item[0]}, {item[1]})",
                      disabled=not discomms_active)
if discomms_active:
    result = filter_discomms(result, discomms)
result = result.loc[result["label"].isin(minor_heads)].reset_index(drop=True)

st.caption("Overall public/private totals and grand totals are excluded.")

if not sources:
    if not select_sources(catalog, year, view):
        st.info("No flat files are available for the selected years and views. No other revision has been substituted.")
    else:
        st.info("No flat file is available for the selected headings, reports and data years.")
    st.stop()

available = {s.heading for s in select_sources(catalog, year, view)}
missing = [h for h in major_heads if h not in available]
if set(major_heads) == set(headings) and missing:
    with st.expander(f"{len(missing)} headings have no flat file for this selection"):
        for name in missing:
            st.write(name)
if (data["sector"] == "Not classified in source").any():
    st.caption("This report contains records marked 'Not classified in source'. Selecting both categories includes them; choosing Public or Private alone does not infer their ownership.")

st.write(f"{len(result):,} matching rows")
if result.empty:
    st.info("No rows match these filters. Try Select all for State, Sector or Category. Public/private totals are unavailable where the source does not classify ownership.")
    st.stop()

output_mode = st.radio("View output as", ["Table", "Graphs"], horizontal=True, key="output_mode")
if output_mode == "Graphs":
    render_graphs(result)
else:
    table = label_columns(result, minor_heads)
    pages = st.columns(2)
    size = pages[0].selectbox("Rows per page", [100, 250, 500], key="page_size", on_change=reset_page)
    max_page = max(1, math.ceil(len(table) / size))
    if not 1 <= st.session_state.get("page", 1) <= max_page:
        st.session_state["page"] = 1
    page = pages[1].number_input("Page", min_value=1, max_value=max_page, step=1, key="page")
    start = (page - 1) * size
    st.caption(f"Rows {start + 1:,}-{min(start + size, len(table)):,} of {len(table):,} | Page {page} of {max_page}")
    st.dataframe(table.iloc[start:start + size], hide_index=True, width="stretch", height=550,
                 column_config={"dc": st.column_config.TextColumn("Discomm", alignment="left"),
                                **{label: st.column_config.TextColumn(label, alignment="right")
                                   for label in minor_heads}})

with st.expander("Source files and column guide"):
    st.write("Discomm shows the original utility or aggregate name. Each selected label is a column, with its original number text right-aligned. Different years, publications, tables, states, utilities and categories remain separate rows. Missing measures are blank.")
    st.write("No totals, ratios or percentages are calculated here. Keep measures, units and aggregation levels separate when analysing these rows.")
    for source in sources:
        st.text(str(source.path.relative_to(source.path.parents[2])))
