import pdfplumber
import pandas as pd
import re
import os
from collections import defaultdict
from config import (
    YEAR_OF_PUBLISHING,
    PDF_FILENAME,
    REPORT_YEAR,
    INPUT_FOLDER,
    OUTPUT_ROOT,
)


# ================================================================
# SETTINGS
# ================================================================

ANNEXURE = "1.2(a)"
TABLE_HEADER = "Cost Structure"


# ALL CSV FILES GO INSIDE THIS ONE FOLDER
OUTPUT_SUBFOLDER = "Cost Structure"
OUTPUT_FOLDER = os.path.join(
    OUTPUT_ROOT,
    OUTPUT_SUBFOLDER,
    REPORT_YEAR
)

# Every PDF this script might be pointed at (23-24.pdf, 22-23.pdf,
# whatever editions you have in INPUT_FOLDER). Add/remove freely --
# each file is scanned independently for every block of this table
# it contains (see find_annexure_blocks below), so this list does
# NOT need to match the years actually present.
INPUT_FILES = [PDF_FILENAME]


# ================================================================
# TABLE SETTINGS
# ================================================================

COLUMNS = [
    "Gross_Input_Energy",
    "Cost_of_Power_Including_Own_Generation",
    "Employee_Cost",
    "Interest_Cost",
    "Depreciation",
    "Other_Costs",
    "ACS"
]

NUM_COLS = 7
UNITS = ["MU", "Rs/kWh", "Rs/kWh", "Rs/kWh", "Rs/kWh", "Rs/kWh", "Rs/kWh"]

TOKEN_RE = re.compile(r'\([\d,]+\.?\d*\)|[\d,]+\.?\d*|-(?=\s|$)')

# How far up from the bottom of the page (in PDF points) to look for
# the printed page number. 1 point ~= 1/72 inch.
PAGE_NUMBER_BOTTOM_MARGIN = 45


STATE_NAMES = [
    "State Sector",
    "Andaman & Nicobar Island",
    "Andaman & Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chattisgarh",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Puducherry",
    "Daman & Diu",
    "Private Sector",
    "Grand Total"
]


skip_patterns = [
    'Cost Structure',
    'Rs /kWh',
    'Gross Input',
    'Cost of Power',
    '(including own',
    'generation)',
    'Employee Cost',
    'Interest Cost',
    'Depreciation',
    'Other Costs',
    'ACS',
    'Annexure',
    'Section 1',
    'Performance of Distribution',
    'Report on Performance of Power Utilities',
    'Dadra & Nagar Haveli and'
]


# ================================================================
# FUNCTIONS
# ================================================================

def clean_number(s):
    if s is None:
        return 0.0

    s = str(s).strip()

    if s in ['-', '', 'None', 'null']:
        return 0.0

    negative = s.startswith('(') and s.endswith(')')

    s = (
        s.replace('(', '')
        .replace(')', '')
        .replace(',', '')
        .replace(' ', '')
    )

    try:
        val = float(s)
        return -val if negative else val
    except:
        return 0.0


def extract_page_number(page, bottom_margin=PAGE_NUMBER_BOTTOM_MARGIN):
    """
    Find the printed page number using word POSITIONS rather than
    text-line order.
    """
    words = page.extract_words()
    if not words:
        return None

    page_height = page.height
    band = [w for w in words if w['top'] > page_height - bottom_margin]

    if not band:
        return None

    lines = defaultdict(list)
    for w in band:
        lines[round(w['top'])].append(w)

    for top in sorted(lines.keys(), reverse=True):
        line_words = sorted(lines[top], key=lambda w: w['x0'])

        for w in reversed(line_words):
            text = w['text'].strip()
            if re.fullmatch(r'\d{1,4}', text):
                return int(text)

    return None


def find_annexure_blocks(pdf, annexure_id, header, max_span=5):
    """
    Locate EVERY occurrence of this annexure's table in the PDF --
    not just the first.

    *** WHY THIS CHANGED ***
    This report repeats each annexure's table THREE times back to
    back: once for the current year, then again for each of the two
    prior years (e.g. Annexure 1.1 appears on pages 26-27 for
    2023-24, again on pages 28-29 for 2022-23, and again on pages
    30-31 for 2021-22 -- all still tagged "Annexure 1.1"). The old
    version of this function did a single forward scan and RETURNED
    as soon as it found the first "Grand Total", so it only ever
    captured the current-year block; the 22-23 and 21-22 blocks
    were silently skipped, and downstream nothing regenerated for
    those "years" (that filename lookup just found no matching PDF
    and moved on).

    This version keeps scanning PAST each block it finds, instead of
    stopping at the first one, and also reads the year label printed
    in each block's own header text (e.g. "2022-23" right under
    "Rs crore") rather than assuming it from a filename -- since all
    three blocks live in the SAME pdf file.

    Returns a list of (year_label, [0-indexed page numbers]) tuples,
    one per block found, in document order (current year first).
    """
    target_tag = f"Annexure {annexure_id}"
    blocks = []
    i = 0
    n = len(pdf.pages)

    while i < n:
        text = pdf.pages[i].extract_text() or ""

        if (
            target_tag in text
            and header in text
            and "State Sector" in text
        ):
            # Two different year-label formats show up in this report:
            # flow-type tables (Revenue, Expense, Profitability, ...)
            # print "2023-24"; point-in-time balance-sheet tables
            # (Total Assets, Total Equity and Liabilities, Net Worth,
            # DSCR) print "As on March 31, 2024" instead. Try both.
            year_match = re.search(r'\b(20\d{2}-\d{2})\b', text)
            if year_match:
                year_label = year_match.group(1)
            else:
                as_on_match = re.search(r'As on March 31,\s*(\d{4})', text)
                if as_on_match:
                    fy_end = int(as_on_match.group(1))
                    year_label = f"{fy_end - 1}-{str(fy_end)[-2:]}"
                else:
                    year_label = None

            pages = [i]

            if "Grand Total" not in text:
                for offset in range(1, max_span):
                    idx = i + offset
                    if idx >= n:
                        break
                    pages.append(idx)
                    if "Grand Total" in (pdf.pages[idx].extract_text() or ""):
                        break

            blocks.append((year_label, pages))
            i = pages[-1] + 1  # resume scanning AFTER this block
        else:
            i += 1

    return blocks


def extract_lines(pdf, page_indices):
    all_lines = []

    for idx in page_indices:

        page = pdf.pages[idx]
        text = page.extract_text()

        if text:

            printed_pg = extract_page_number(page)

            for line in text.split('\n'):
                all_lines.append(
                    (line, printed_pg)
                )

    return all_lines


def get_values(raw_tokens):
    tokens = list(raw_tokens)

    for _ in range(5):

        if len(tokens) <= NUM_COLS:
            break

        merged = False

        for i in range(len(tokens) - 1):

            t = tokens[i]
            next_t = tokens[i + 1]

            if (
                re.match(r'^\(?\d{1,3}$', t)
                and re.match(r'^[,.]', next_t)
                and next_t != '-'
            ):
                tokens = (
                    tokens[:i]
                    + [t + next_t]
                    + tokens[i + 2:]
                )

                merged = True
                break

        if not merged:
            break

    while len(tokens) < NUM_COLS:
        tokens.append("-")

    return tokens[:NUM_COLS]


def parse(lines, year_of_data):

    start_idx = next(
        (
            i
            for i, (line, pg) in enumerate(lines)
            if 'State Sector' in line
        ),
        None
    )

    if start_idx is None:
        return []

    records = []

    current_state = None
    current_sector = "Public"

    for line, pg in lines[start_idx:]:

        line = line.strip()

        if not line:
            continue

        if any(p in line for p in skip_patterns):
            continue

        if 'Private Sector' in line:
            current_sector = "Private"

        token_matches = list(
            TOKEN_RE.finditer(line)
        )

        if not token_matches:
            continue

        first_pos = token_matches[0].start()

        name = line[:first_pos].strip()

        if not name:
            continue

        raw_tokens = [
            match.group()
            for match in token_matches
        ]

        values = get_values(raw_tokens)

        if name == "Grand Total":
            row_type = "grand_total"

        elif name in STATE_NAMES:
            row_type = "state_aggregate"

        else:
            row_type = "utility"

        if row_type in (
            "state_aggregate",
            "grand_total"
        ):
            current_state = name

        for j, column in enumerate(COLUMNS):

            records.append({
                "yop": YEAR_OF_PUBLISHING,
                "yod": year_of_data,
                "ann": ANNEXURE,
                "header": TABLE_HEADER,

                "st": (
                    current_state
                    if row_type == "utility"
                    else name
                ),

                "dc": name,
                "row_type": row_type,
                "sector": current_sector,
                "label": column,
                "unit": UNITS[j],
                "number": clean_number(values[j]),
                "pg": pg,
            })

    return records


# ================================================================
# PROCESS ONE PDF FILE (may yield MULTIPLE years' worth of CSVs)
# ================================================================

def process_file(pdf_filename):

    pdf_path = os.path.join(INPUT_FOLDER, pdf_filename)

    if not os.path.exists(pdf_path):
        print(f"{pdf_filename}: PDF not found")
        return

    with pdfplumber.open(pdf_path) as pdf:

        blocks = find_annexure_blocks(pdf, ANNEXURE, TABLE_HEADER)

        if not blocks:
            print(f"{pdf_filename}: could not locate Annexure {ANNEXURE} table")
            return

        for year_label, page_indices in blocks:

            if year_label is None:
                print(f"{pdf_filename}: found a block at pages {page_indices} but couldn't read its year label -- skipping")
                continue

            lines = extract_lines(pdf, page_indices)

            records = parse(lines, year_label)

            if not records:
                print(f"{pdf_filename} [{year_label}]: No data found")
                continue

            # Puducherry patch
            for rec in records:
                if "Puducherry" in rec["dc"]:
                    rec["st"] = "Puducherry"

            df = pd.DataFrame(records)

            short_year = year_label[2:4] + "-" + year_label[5:7]

            output_path = os.path.join(
                OUTPUT_FOLDER,
                f"Cost-Structure-{short_year}.csv"
            )

            df.to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig"
            )

            missing_pg = df["pg"].isna().sum()
            if missing_pg:
                print(f"{pdf_filename} [{year_label}]: WARNING - {missing_pg} rows missing a page number")

            print(f"{pdf_filename} [{year_label}]: Done (pages {page_indices})")


# ================================================================
# RUN
# ================================================================

def main():

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for pdf_filename in INPUT_FILES:

        try:
            process_file(pdf_filename)

        except Exception as e:
            print(f"{pdf_filename}: Error - {e}")


if __name__ == "__main__":
    main()