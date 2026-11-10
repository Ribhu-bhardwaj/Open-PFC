"""Read existing flat files. This module never writes to the source directory."""
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import csv
import re

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs" if (ROOT / "outputs/flat-files-index.csv").is_file() else Path(__file__).resolve().parent / "data"
FIELDS = ["yop", "yod", "ann", "header", "st", "dc", "row_type", "sector", "label", "unit", "number", "pg"]
VIEWS = {"Preliminary": 0, "Revision 1": 1, "Revision 2": 2}
REPORTS = {f"{n:02d}-{n + 1:02d}" for n in range(18, 25)}
OVERALL_NAMES = {"State Sector", "Private Sector", "Grand Total"}
NON_STATES = OVERALL_NAMES | {"DISCOMS", "GEDCO/ Integrated Utilities", "Power Departments"}


@dataclass(frozen=True)
class Source:
    report: str
    year: str
    heading: str
    path: Path
    annexure: str = ""


def annexure_key(value):
    """Numeric annexure order, including lettered sub-annexures and 1.10."""
    match = re.search(r"(\d+(?:\.\d+)*)(.*)", str(value).strip())
    if not match:
        return (1, (), str(value).casefold())
    return (0, tuple(int(n) for n in match[1].split(".")),
            re.sub(r"[^a-z0-9]", "", match[2].casefold()))


def heading_options(catalog, year, view):
    """Available headings follow this edition; unavailable headings follow last."""
    selected = select_sources(catalog, year, view)
    available = {}
    for source in selected:
        available[source.heading] = min(available.get(source.heading, source.annexure),
                                         source.annexure, key=annexure_key)
    fallback = {}
    for source in sorted(catalog, key=lambda s: s.report):
        fallback[source.heading] = source.annexure
    return ["All"] + sorted(fallback, key=lambda h: (
        h not in available, annexure_key(available.get(h, fallback[h])), h.casefold()))


def financial_year(start):
    return f"{start:04d}-{(start + 1) % 100:02d}"


def report_for(year, view):
    start = int(year[:4]) + VIEWS[view]
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def choices(value):
    return [value] if isinstance(value, str) else list(value)


def read_catalog(outputs=OUTPUTS):
    outputs = Path(outputs).resolve()
    index = outputs / "flat-files-index.csv"
    result = []
    seen = set()
    with index.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["schema"] != "modern_12_columns" or row["report_year"] not in REPORTS:
                continue
            parts = PureWindowsPath(row["file"]).parts
            path = outputs.joinpath(*parts).resolve()
            if not path.is_relative_to(outputs) or not path.is_file():
                raise ValueError(f"Invalid or missing indexed source: {row['file']}")
            match = re.search(r"-(\d{2})-(\d{2})\.csv$", path.name)
            if not match or int(match[2]) != (int(match[1]) + 1) % 100:
                raise ValueError(f"Cannot identify data year: {path.name}")
            year = financial_year(2000 + int(match[1]))
            offset = 2000 + int(row["report_year"][:2]) - int(year[:4])
            if offset not in VIEWS.values():
                raise ValueError(f"Unexpected report/data-year combination: {row['file']}")
            key = (row["report_year"], year, row["table"])
            if key in seen:
                raise ValueError(f"Duplicate indexed source: {key}")
            seen.add(key)
            with path.open(encoding="utf-8-sig", newline="") as source_stream:
                first = next(csv.DictReader(source_stream), None)
            if not first or not first.get("ann"):
                raise ValueError(f"Missing annexure in {path.name}")
            result.append(Source(row["report_year"], year, row.get("heading") or parts[0], path, first["ann"]))
    if not result:
        raise ValueError("No indexed flat files found for report editions 2018-19 through 2024-25.")
    return sorted(result, key=lambda s: (s.report, s.year, annexure_key(s.annexure), s.heading.casefold()))


def select_sources(catalog, year, view, heading="All"):
    pairs = {(report_for(y, v), y) for y in choices(year) for v in choices(view)}
    headings = choices(heading)
    return [s for s in catalog if (s.report, s.year) in pairs
            and ("All" in headings or s.heading in headings)]


def read_sources(sources):
    frames = []
    for source in sources:
        frame = pd.read_csv(source.path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if list(frame.columns) != FIELDS:
            raise ValueError(f"Unexpected columns in {source.path.name}")
        if frame.empty or set(frame["yod"]) != {source.year}:
            raise ValueError(f"Data-year mismatch or empty file: {source.path.name}")
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=FIELDS)
    combined = pd.concat(frames, ignore_index=True)
    # Stable sorting preserves the source's state, utility and measure sequence.
    return combined.sort_values("ann", key=lambda s: s.map(annexure_key),
                                kind="stable").reset_index(drop=True)


def state_names(frame):
    return sorted(set(frame["st"]) - NON_STATES - {""}, key=str.casefold)


def filter_records(frame, state="All", row_type="All", sector="All", totals_only=False):
    states, types, sectors = choices(state), choices(row_type), choices(sector)
    if totals_only:
        if "All" in sectors:
            mask = (frame["row_type"] == "grand_total") & (frame["sector"] == "All")
        else:
            mask = pd.Series(False, index=frame.index)
            for selected in sectors:
                name = "State Sector" if selected == "Public" else "Private Sector"
                mask |= (frame["dc"] == name) & (frame["sector"] == selected)
        # Overall source totals have no individual state or utility dimension.
        return frame.loc[mask, FIELDS].reset_index(drop=True)
    mask = ~frame["dc"].isin(OVERALL_NAMES) & (frame["row_type"] != "grand_total")
    if "All" not in states:
        mask &= frame["st"].isin(states)
    if "All" not in types:
        mapping = {"State aggregate": "state_aggregate", "Utility": "utility"}
        mask &= frame["row_type"].isin([mapping[t] for t in types])
    if "All" not in sectors:
        mask &= frame["sector"].isin(sectors)
    return frame.loc[mask, FIELDS].reset_index(drop=True)
