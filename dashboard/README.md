# PFC-Report on discomms-Dashboard

Read-only Streamlit dashboard for the existing flat files from report editions 2018-19 through 2024-25. Everything added for the dashboard is contained in this directory. The extraction scripts, input PDFs and output CSVs are not modified.

## Start

From the csep-hermes root, run:

```powershell
.\dashboard\run_dashboard.ps1
```

Open http://localhost:8501 in your browser. Keep that terminal running; Ctrl+C stops the dashboard. Use `-Port 8502` if 8501 is occupied. There is no custom CSS, theme, charting or editing interface: the app uses standard Streamlit controls and a read-only dataframe.

The dashboard has its own environment under `dashboard/.venv`. To recreate it, run `dashboard/setup.ps1`. This installs dashboard dependencies without changing the extraction environment.

## Filters

- **Select year** means the data year (`yod`). All data years carried by the included reports are accessible. This includes 2016-17 and 2017-18, which appear as revisions in the earliest included reports.
- **Select view** uses a fixed report-year offset. Preliminary reads the same-year report; Revision 1 reads the report one year later; Revision 2 reads the report two years later. For 2022-23, these are reports 2022-23, 2023-24 and 2024-25 respectively. Missing revisions never fall back to another version.
- **Heading** uses the output-folder names, prefixed by the selected report's annexure number. All remains first, followed by available headings in numeric annexure order: 1.1, 1.1(a), 1.1(b), 1.2, ... 1.9, 1.10. Unavailable headings appear last without a number. The order is taken from each report's actual CSVs, so changes to annexure numbering across editions are respected. Results use the same numeric order and retain source row order within each annexure.
- **State (st)** lists available state/UT names exactly as stored. It excludes overall and operational group labels from the choices. All removes the state restriction.
- **Type** has All, State aggregate and Utility. All includes ordinary rows of any source type, including the older operational aggregates, but excludes the overall sector totals and grand totals.
- **Sector** has All, Public and Private. In ordinary browsing, All also includes records marked Not classified in source. These records are not silently assigned public/private ownership.
- **Totals only** switches to published overall totals. Public selects State Sector; Private selects Private Sector; All selects Grand Total. State and Type reset to All and are disabled because these totals cover the whole report. Reports without public/private classifications show no corresponding subtotal rather than invent one.

Results preserve the original 12 columns and their values: `yop, yod, ann, header, st, dc, row_type, sector, label, unit, number, pg`. They are shown as text to preserve the CSV representation. The app does not add, average, round or otherwise recalculate values. Pagination displays 100, 250 or 500 rows at a time. The selected report edition is displayed above the filters; source file paths are available below the table.

## Files in this folder

- `app.py`: Streamlit page, controls and pagination.
- `data_access.py`: source discovery, revision selection and read-only filtering.
- `run_dashboard.ps1`: starts the local dashboard.
- `setup.ps1` and `requirements.txt`: dashboard-only environment setup.
- `.streamlit/config.toml`: server defaults and disabled usage telemetry; the local launcher explicitly binds to localhost.
- `prepare_cloud_data.py`: creates byte-identical copies of the 318 relevant CSVs inside `data/`, with a filtered index for hosting.
- `cloud-data-integrity.json`: fingerprints of those hosted copies.
- `tests/test_dashboard.py`: real-file and interface checks.
- `source-integrity.json`: fingerprints taken before development for every indexed flat file and the index. This is verification evidence, not a dashboard input.

The app reads `../outputs/flat-files-index.csv` and only the modern flat files it lists for the selected report editions. It does not read supporting cells, historical tables, review files or backups. CSVs are loaded into memory and cached in memory only; source modification time and size invalidate that cache. There are no source-writing calls or editable data widgets.

## Streamlit Community Cloud

On a host without the original `outputs` directory, the app automatically reads `dashboard/data` instead. This is a snapshot; it does not synchronize from this computer. To refresh it after an intentional source update, run from the project root:

```powershell
.\dashboard\.venv\Scripts\python.exe dashboard\prepare_cloud_data.py
```

Commit the updated dashboard code and data to the deployment branch. Community Cloud coordinates:

- Repository: `Ribhu-bhardwaj/Open-PFC`
- Branch: `codex/dashboard-streamlit`
- Entrypoint: `dashboard/app.py`
- Python: `3.12` (under Advanced settings)
- Dependencies: `dashboard/requirements.txt`

The deployment branch contains the dashboard and its data copies; unrelated local extraction changes are not included. `.publish/` is an ignored, isolated checkout used to publish that branch without modifying the main working tree's Git index or branch. No credentials or virtual environment are published.

Open [Streamlit Community Cloud](https://share.streamlit.io/), create an app from the repository coordinates above, and deploy. See the [official deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy). Account sign-in is required. Preparation of these files alone does not mean the app has been deployed.

## Verify

From the dashboard directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover all indexed sources, the three 2022-23 revisions, unavailable revisions, public/private/combined totals, unknown ownership, ordinary filters, pagination, displayed columns and source-file integrity. If someone intentionally changes a flat file later, the saved fingerprint check will report it; the dashboard itself can read updated files without replacing that evidence automatically.

Framework references: [Streamlit dataframe](https://docs.streamlit.io/develop/api-reference/data/st.dataframe) and [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
