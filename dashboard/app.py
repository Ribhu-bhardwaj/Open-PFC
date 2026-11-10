"""Local, read-only Streamlit view of the existing flat files."""
import math
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_access import (FIELDS, VIEWS, read_catalog, read_sources, select_sources,
                         report_for, state_names, filter_records, heading_options)

st.set_page_config(page_title="PFC-Report on discomms-Dashboard", layout="wide")


@st.cache_data(show_spinner=False, max_entries=24)
def load_files(sources, signatures):
    # Signatures invalidate memory-only caching when the underlying files change.
    return read_sources(sources)


def reset_page():
    st.session_state["page"] = 1


def change_filter(key):
    selected = st.session_state[key]
    if "All" in selected and len(selected) > 1:
        st.session_state[key] = ["All"] if selected[-1] == "All" else [v for v in selected if v != "All"]
    reset_page()


def change_totals():
    reset_page()
    if st.session_state.get("totals_only"):
        st.session_state["state"] = ["All"]
        st.session_state["row_type"] = ["All"]


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
first = st.columns(3)
year = first[0].multiselect("Select year", years, default=[years[0]], key="year", on_change=reset_page,
                        help="The data year (yod), not the report edition.")
view = first[1].multiselect("Select view", list(VIEWS), default=["Preliminary"], key="view", on_change=reset_page,
                        help="Preliminary: same-year report. Revision 1: next report. Revision 2: report two years later.")
headings = heading_options(catalog, year, view)
selected_annexures = {}
for source in reversed(select_sources(catalog, year, view)):
    selected_annexures[source.heading] = source.annexure
heading = first[2].multiselect("Heading", headings, default=["All"], key="heading", on_change=change_filter, args=("heading",),
                           format_func=lambda h: f"{selected_annexures[h]} — {h}" if h in selected_annexures else h)
reports = list(dict.fromkeys("20" + report_for(y, v) for y in year for v in view))
st.caption(f"Data year: {', '.join(year)} | View: {', '.join(view)} | Source report: {', '.join(reports)}")

sources = select_sources(catalog, year, view, heading)
try:
    signatures = tuple((str(s.path), s.path.stat().st_mtime_ns, s.path.stat().st_size) for s in sources)
    data = load_files(tuple(sources), signatures)
except (OSError, ValueError, KeyError) as exc:
    st.error(f"Unable to read the selected flat files: {exc}")
    st.stop()

totals_only = st.checkbox("Totals only", key="totals_only", on_change=change_totals,
                          help="Public: State Sector total. Private: Private Sector total. All: combined Grand Total.")
states = ["All"] + state_names(data)
if any(s not in states for s in st.session_state.get("state", ["All"])):
    st.session_state["state"] = ["All"]
second = st.columns(3)
state = second[0].multiselect("State (st)", states, default=["All"], key="state", on_change=change_filter, args=("state",), disabled=totals_only)
row_type = second[1].multiselect("Type", ["All", "State aggregate", "Utility"], default=["All"], key="row_type",
                              on_change=change_filter, args=("row_type",), disabled=totals_only)
sector = second[2].multiselect("Sector", ["All", "Public", "Private"], default=["All"], key="sector", on_change=change_filter, args=("sector",))

if totals_only:
    st.caption("Overall totals only. State and Type do not apply. Published totals are displayed without recalculation.")
else:
    st.caption("Overall public/private totals and grand totals are excluded. All means no restriction within ordinary rows.")

if not sources:
    if not select_sources(catalog, year, view):
        st.info("No flat files are available for the selected years and views. No other revision has been substituted.")
    else:
        st.info("No flat file is available for the selected headings, reports and data years.")
    st.stop()

available = {s.heading for s in select_sources(catalog, year, view)}
if "All" in heading and len(available) < len(headings) - 1:
    missing = [h for h in headings[1:] if h not in available]
    with st.expander(f"{len(missing)} headings have no flat file for this selection"):
        for name in missing:
            st.write(name)
if (data["sector"] == "Not classified in source").any():
    st.caption("This report contains records marked 'Not classified in source'. Ordinary Sector = All includes them; Public/Private selections do not infer their ownership.")

result = filter_records(data, state, row_type, sector, totals_only)
st.write(f"{len(result):,} matching rows")
if result.empty:
    st.info("No rows match these filters. Try All for State, Type or Sector. Public/private totals are unavailable where the source does not classify ownership.")
    st.stop()

pages = st.columns(2)
size = pages[0].selectbox("Rows per page", [100, 250, 500], key="page_size", on_change=reset_page)
max_page = max(1, math.ceil(len(result) / size))
if not 1 <= st.session_state.get("page", 1) <= max_page:
    st.session_state["page"] = 1
page = pages[1].number_input("Page", min_value=1, max_value=max_page, step=1, key="page")
start = (page - 1) * size
st.caption(f"Rows {start + 1:,}-{min(start + size, len(result)):,} of {len(result):,} | Page {page} of {max_page}")
st.dataframe(result.iloc[start:start + size][FIELDS], hide_index=True, width="stretch", height=550)

with st.expander("Source files and column guide"):
    st.write("Columns retain the flat-file order and values. yop = publication label; yod = data year; ann = annexure; st = state; dc = utility/aggregate; pg = printed PDF page. label, unit and number describe each measure.")
    st.write("No totals, ratios or percentages are calculated here. Keep measures, units and aggregation levels separate when analysing these rows.")
    for source in sources:
        st.text(str(source.path.relative_to(source.path.parents[2])))
