# PFC-Report on discomms-Dashboard

Read-only Streamlit dashboard for the existing flat files from report editions 2018-19 through 2024-25. Everything added for the dashboard is contained in this directory. The extraction scripts, input PDFs and output CSVs are not modified.

## Start

From the csep-hermes root, run:

```powershell
.\dashboard\run_dashboard.ps1
```

Open http://localhost:8501 in your browser. Keep that terminal running; Ctrl+C stops the dashboard. Use `-Port 8502` if 8501 is occupied. The app uses standard Streamlit controls, a read-only table, and Altair graphs without custom CSS or an editing interface.

The dashboard has its own environment under `dashboard/.venv`. To recreate it, run `dashboard/setup.ps1`. This installs dashboard dependencies without changing the extraction environment.

## Filters

See [decision.md](decision.md) for the current filter behavior. Totals only has been removed; overall sector totals and Grand Totals remain excluded.

- **Select year** means the data year (`yod`). All data years carried by the included reports are accessible. This includes 2016-17 and 2017-18, which appear as revisions in the earliest included reports.
- **Select view** defaults to Latest available, choosing the newest catalog report per data year. Preliminary, Revision 1, and Revision 2 remain available for comparison. Missing fixed revisions are not substituted.
- **Category** selects Public and/or Private. Selecting both also includes ownership marked Not classified in source, without guessing its category.
- **Sector** selects State aggregate and/or Utility. Overall public/private totals and Grand Totals remain excluded.
- **State (st)** lists original state/UT names. **Discomms** selects utilities within the chosen states and categories.
- **Major Heads** lists every table, including Revenue Structure and other lettered annexures, in numeric annexure order without number prefixes.
- **Minor Heads** selects the original `label` measures in the selected tables. Shared labels select corresponding rows in every selected table; units are not combined.

All filters support multiple selections and native Select all. Clear All empties them, including Select view. All available measures are selected initially.

**Table** shows only `label` and `number` in their original text representation, with 100, 250 or 500 rows per page. Repeated labels remain separate source rows. **Graphs** offers bar comparisons for a chosen year and line trends across selected years. Graph choices separate tables, units and aggregation levels; publications remain distinct and source details are visible on hover. Graphs use the full filtered result, not just the table page. No rows are summed or averaged. See [decision.md](decision.md) for all design decisions, function explanations and diagrams.

## Files in this folder

- `app.py`: Streamlit page, controls and pagination.
- `charts.py`: chart measure selection, numeric parsing, bar comparisons and year trends.
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

The [hosted dashboard](https://open-pfc-vvwuqyzb8npyjsgmjjfqqz.streamlit.app/?embed=true) reads the snapshot in GitHub. Publish dashboard changes to the following coordinates to update the live app:

- Repository: `Ribhu-bhardwaj/Open-PFC`
- Live branch: `main`; the initial dashboard was prepared on `codex/dashboard-streamlit`.
- Entrypoint: `dashboard/app.py`
- Python: the live host uses `3.14`; the local dashboard was tested on `3.12`.
- Dependencies: `dashboard/requirements.txt`

The deployment branch contains the dashboard and its data copies; unrelated local extraction changes are not included. `.publish/` is an ignored, isolated checkout used to publish that branch without modifying the main working tree's Git index or branch. No credentials or virtual environment are published.

Manage the existing app in [Streamlit Community Cloud](https://share.streamlit.io/). See the [official deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) if a new deployment is needed.

## Verify

From the dashboard directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover all indexed sources, the three 2022-23 revisions, unavailable revisions, public/private/combined totals, unknown ownership, ordinary filters, pagination, displayed columns and source-file integrity. If someone intentionally changes a flat file later, the saved fingerprint check will report it; the dashboard itself can read updated files without replacing that evidence automatically.

Framework references: [Streamlit dataframe](https://docs.streamlit.io/develop/api-reference/data/st.dataframe) and [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
