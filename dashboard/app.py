"""Local, read-only Streamlit view of the existing flat files."""
import math
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_access import (FIELDS, VIEWS, read_catalog, read_sources, select_sources,
                         report_for, state_names, filter_records, head_groups)

st.set_page_config(page_title="PFC-Report on discomms-Dashboard", layout="wide")


@st.cache_data(show_spinner=False, max_entries=24)
def load_files(sources, signatures):
    # Signatures invalidate memory-only caching when the underlying files change.
    return read_sources(sources)


def reset_page():
    st.session_state["page"] = 1


def multiselect(container, label, options, *, key, default=None, **kwargs):
    """Keep stored choices valid and migrate the former All entry."""
    if key in st.session_state:
        selected = st.session_state[key]
        previous_options = st.session_state.get(f"{key}_options")
        all_selected = default is None and previous_options is not None and set(selected) == set(previous_options)
        valid = list(options) if "All" in selected or all_selected else [
            value for value in selected if value in options]
        if valid != selected:
            st.session_state[key] = valid
        default = None
    elif default is None:
        default = options
    st.session_state[f"{key}_options"] = list(options)
    return container.multiselect(label, options, default=default,
                                 key=key, on_change=reset_page, select_all=True, **kwargs)


def change_totals():
    reset_page()
    if st.session_state.get("totals_only"):
        st.session_state.pop("state", None)
        st.session_state.pop("row_type", None)


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
additional = st.columns(2)
year = first[0].multiselect("Select year", years, default=[years[0]], key="year", on_change=reset_page,
                        help="The data year (yod), not the report edition.")
view = additional[0].multiselect("Select view", list(VIEWS), default=["Preliminary"], key="view", on_change=reset_page,
                        help="Preliminary: same-year report. Revision 1: next report. Revision 2: report two years later.")
totals_only = additional[1].checkbox("Totals only", key="totals_only", on_change=change_totals,
                          help="Public: State Sector total. Private: Private Sector total. Both selected: combined Grand Total.")
sector = multiselect(first[1], "Category", ["Public", "Private"], key="sector")
row_type = multiselect(first[2], "Sector", ["State aggregate", "Utility"], key="row_type", disabled=totals_only)
groups = head_groups(catalog, year, view)
major_heads = multiselect(first[4], "Major Heads", list(groups), key="major_heads")
minor_options = [minor for major, minors in groups.items() if major in major_heads for minor in minors]
minor_heads = multiselect(first[5], "Minor Heads", minor_options, key="minor_heads", default=[])
heading = major_heads + minor_heads
reports = list(dict.fromkeys("20" + report_for(y, v) for y in year for v in view))
st.caption(f"Data year: {', '.join(year)} | View: {', '.join(view)} | Source report: {', '.join(reports)}")

sources = select_sources(catalog, year, view, heading)
try:
    signatures = tuple((str(s.path), s.path.stat().st_mtime_ns, s.path.stat().st_size) for s in sources)
    data = load_files(tuple(sources), signatures)
except (OSError, ValueError, KeyError) as exc:
    st.error(f"Unable to read the selected flat files: {exc}")
    st.stop()

states = state_names(data)
state = multiselect(first[3], "State (st)", states, key="state", disabled=totals_only)

if totals_only:
    st.caption("Overall totals only. State and Sector do not apply. Published totals are displayed without recalculation.")
else:
    st.caption("Overall public/private totals and grand totals are excluded.")

if not sources:
    if not select_sources(catalog, year, view):
        st.info("No flat files are available for the selected years and views. No other revision has been substituted.")
    else:
        st.info("No flat file is available for the selected headings, reports and data years.")
    st.stop()

available = {s.heading for s in select_sources(catalog, year, view)}
missing = [h for h in major_heads if h not in available]
if set(major_heads) == set(groups) and missing:
    with st.expander(f"{len(missing)} headings have no flat file for this selection"):
        for name in missing:
            st.write(name)
if (data["sector"] == "Not classified in source").any():
    st.caption("This report contains records marked 'Not classified in source'. Selecting both categories includes them; choosing Public or Private alone does not infer their ownership.")

category_filter = "All" if set(sector) == {"Public", "Private"} else sector
result = filter_records(data, state, row_type, category_filter, totals_only)
st.write(f"{len(result):,} matching rows")
if result.empty:
    st.info("No rows match these filters. Try Select all for State, Sector or Category. Public/private totals are unavailable where the source does not classify ownership.")
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
