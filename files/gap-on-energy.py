import pdfplumber
import pandas as pd
import re
import os
from collections import defaultdict


# ================================================================
# SETTINGS
# ================================================================

YEAR_OF_PUBLISHING = "Feb 2025"

ANNEXURE = "1.3(a)"
TABLE_HEADER = "Gap on Energy Sold basis"

INPUT_FOLDER = r"C:\Users\ribhu\csep-hermes\input"

# All three year CSVs are written flat into this single folder.
OUTPUT_FOLDER = (
    r"C:\Users\ribhu\csep-hermes\outputs\Gap on Energy Sold basis\23-23"
)

INPUT_FILES = ["23-24.pdf"]


# ================================================================
# TABLE SETTINGS
# ================================================================

COLUMNS = [
    "ACS_on_Energy_Sold_Basis",
    "ARR_on_Energy_Sold_Excl_Reg_Income_and_Revenue_Grant_UDAY",
    "Gap_on_Energy_Sold"
]

UNITS = ["Rs/kWh", "Rs/kWh", "Rs/kWh"]

# This annexure prints THREE years side-by-side on the same row.
# Each year has the same 3 measures, so every data row contains 9 values.
EXPECTED_YEAR_COUNT = 3
FALLBACK_YEARS = ["2023-24", "2022-23", "2021-22"]
COLS_PER_YEAR = len(COLUMNS)
NUM_COLS = COLS_PER_YEAR * EXPECTED_YEAR_COUNT  # 3 x 3 = 9

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
    'Gap on Energy Sold basis',
    'Rs./kWh',
    'Rs./kWh',
    'ARR on Energy',
    'Gap on Energy',
    'Sold (excluding',
    'Regulatory',
    'Income and',
    'Revenue Grant',
    'ACS on',
    'under UDAY',
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
    except ValueError:
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


def extract_table_years(text, expected_count=EXPECTED_YEAR_COUNT):
    """
    Read the year labels printed across the table header, preserving
    left-to-right order. For this table that should be:
        2023-24, 2022-23, 2021-22
    """
    years = []

    for match in re.finditer(r'\b20\d{2}-\d{2}\b', text or ""):
        year = match.group(0)
        if year not in years:
            years.append(year)

        if len(years) == expected_count:
            break

    return years


def find_annexure_blocks(pdf, annexure_id, header, max_span=5):
    """
    Find the page span(s) containing this annexure table.

    IMPORTANT FOR THIS TABLE:
    The three data years are NOT three separate vertical table blocks.
    They are three column groups printed side-by-side in the SAME table:

        2023-24 -> ACS, ARR, Gap
        2022-23 -> ACS, ARR, Gap
        2021-22 -> ACS, ARR, Gap

    Therefore this function only finds the table's page span. The year
    split happens later while parsing the 9 numeric values in each row.
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
            pages = [i]

            if "Grand Total" not in text:
                for offset in range(1, max_span):
                    idx = i + offset
                    if idx >= n:
                        break

                    pages.append(idx)

                    if "Grand Total" in (pdf.pages[idx].extract_text() or ""):
                        break

            blocks.append(pages)
            i = pages[-1] + 1
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
                all_lines.append((line, printed_pg))

    return all_lines


def get_values(raw_tokens, num_cols=NUM_COLS):
    """
    Normalise the row to exactly 9 numeric cells:
      3 cells for 2023-24 + 3 for 2022-23 + 3 for 2021-22.
    """
    tokens = list(raw_tokens)

    # Preserve the old repair logic for numbers that pdfplumber may
    # split into two tokens.
    for _ in range(10):
        if len(tokens) <= num_cols:
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

    while len(tokens) < num_cols:
        tokens.append("-")

    return tokens[:num_cols]


def parse(lines, years_of_data):
    """
    Parse one row containing all 3 years and emit long-format records.

    Example row values:
      8.56 8.34 0.22 | 8.54 7.74 0.80 | 7.61 7.31 0.30

    becomes 9 records total: 3 labels for each of the 3 years.
    """
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

    required_values = len(years_of_data) * COLS_PER_YEAR

    for line, pg in lines[start_idx:]:
        line = line.strip()

        if not line:
            continue

        if any(p in line for p in skip_patterns):
            continue

        if 'Private Sector' in line:
            current_sector = "Private"

        token_matches = list(TOKEN_RE.finditer(line))

        if not token_matches:
            continue

        first_pos = token_matches[0].start()
        name = line[:first_pos].strip()

        if not name:
            continue

        raw_tokens = [match.group() for match in token_matches]
        values = get_values(raw_tokens, required_values)

        if name == "Grand Total":
            row_type = "grand_total"
        elif name in STATE_NAMES:
            row_type = "state_aggregate"
        else:
            row_type = "utility"

        if row_type in ("state_aggregate", "grand_total"):
            current_state = name

        # Split the 9 values into 3 year-groups of 3 columns each.
        for year_idx, year_of_data in enumerate(years_of_data):
            base = year_idx * COLS_PER_YEAR

            for col_idx, column in enumerate(COLUMNS):
                value_idx = base + col_idx

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
                    "unit": UNITS[col_idx],
                    "number": clean_number(values[value_idx]),
                    "pg": pg,
                })

    return records


# ================================================================
# PROCESS ONE PDF FILE -> ONE CSV PER YEAR
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

        # Accumulate in case the annexure spans more than one detected block.
        records_by_year = defaultdict(list)

        for page_indices in blocks:
            block_text = "\n".join(
                (pdf.pages[idx].extract_text() or "")
                for idx in page_indices
            )

            years = extract_table_years(block_text)

            if len(years) != EXPECTED_YEAR_COUNT:
                print(
                    f"{pdf_filename}: expected {EXPECTED_YEAR_COUNT} year labels "
                    f"in table header but found {years}. "
                    f"Using fallback years {FALLBACK_YEARS}."
                )
                years = FALLBACK_YEARS.copy()

            print(f"{pdf_filename}: detected table years -> {', '.join(years)}")

            lines = extract_lines(pdf, page_indices)
            records = parse(lines, years)

            if not records:
                print(f"{pdf_filename}: No data found on pages {page_indices}")
                continue

            # Puducherry patch
            for rec in records:
                if "Puducherry" in rec["dc"]:
                    rec["st"] = "Puducherry"

                records_by_year[rec["yod"]].append(rec)

        if not records_by_year:
            print(f"{pdf_filename}: no output records created")
            return

        # Write three independent CSVs, one for each year.
        for year_label in FALLBACK_YEARS:
            year_records = records_by_year.get(year_label, [])

            if not year_records:
                print(f"{pdf_filename} [{year_label}]: No data found")
                continue

            df = pd.DataFrame(year_records)
            short_year = year_label[2:4] + "-" + year_label[5:7]

            output_path = os.path.join(
                OUTPUT_FOLDER,
                f"Gap-on-Energy-Sold-basis-{short_year}.csv"
            )

            df.to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig"
            )

            missing_pg = df["pg"].isna().sum()
            if missing_pg:
                print(
                    f"{pdf_filename} [{year_label}]: WARNING - "
                    f"{missing_pg} rows missing a page number"
                )

            print(
                f"{pdf_filename} [{year_label}]: Done -> {output_path}"
            )


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