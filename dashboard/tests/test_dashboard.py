import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
from data_access import (FIELDS, VIEWS, OUTPUTS, OVERALL_NAMES, NON_STATES, read_catalog,
                         read_sources, select_sources, report_for, filter_records, state_names,
                         annexure_key, heading_options, head_groups)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_catalog()
        cls.heading = next(s.heading for s in cls.catalog if s.path.name.startswith("Revenue-details-"))

    def test_every_indexed_modern_file_is_reachable_by_one_revision(self):
        index = OUTPUTS / "flat-files-index.csv"
        with index.open(encoding="utf-8-sig", newline="") as stream:
            expected = [r for r in csv.DictReader(stream) if r["schema"] == "modern_12_columns"
                        and r["report_year"] in {f"{n:02d}-{n+1:02d}" for n in range(18, 25)}]
        reached = []
        for year in {s.year for s in self.catalog}:
            for view in VIEWS:
                reached.extend(select_sources(self.catalog, year, view))
        self.assertEqual(len(reached), len(expected))
        self.assertEqual(len({s.path for s in reached}), len(expected))
        self.assertTrue(all("_historical_tables" not in str(s.path) for s in reached))

    def test_numeric_annexure_order_and_every_report_heading_order(self):
        expected = ["1.1", "1.1(a)", "1.1(b)", "1.2", "1.9", "1.10", "1.11", "2.1"]
        self.assertEqual(sorted(reversed(expected), key=annexure_key), expected)
        for year in {s.year for s in self.catalog}:
            for view in VIEWS:
                sources = select_sources(self.catalog, year, view)
                options = heading_options(self.catalog, year, view)
                self.assertNotIn("All", options)
                self.assertEqual(options[:len(sources)], [s.heading for s in sources])
                keys = [annexure_key(s.annexure) for s in sources]
                self.assertEqual(keys, sorted(keys))

    def test_display_annexures_sorted_even_with_reversed_source_order(self):
        sources = select_sources(self.catalog, "2024-25", "Preliminary")
        frame = read_sources(list(reversed(sources)))
        keys = [annexure_key(value) for value in frame["ann"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(frame.iloc[0]["ann"], "1.1")

    def test_cloud_copies_match_sources_and_catalog(self):
        if OUTPUTS == DASHBOARD / "data":
            self.skipTest("Original extraction outputs are not present in this checkout")
        copied = read_catalog(DASHBOARD / "data")
        self.assertEqual(len(copied), len(self.catalog))
        for original, copy in zip(self.catalog, copied):
            self.assertEqual((original.report, original.year, original.heading, original.annexure),
                             (copy.report, copy.year, copy.heading, copy.annexure))
            self.assertEqual(original.path.read_bytes(), copy.path.read_bytes())

    def test_three_2022_revisions_match_the_actual_source_records(self):
        for view, edition in [("Preliminary", "22-23"), ("Revision 1", "23-24"), ("Revision 2", "24-25")]:
            with self.subTest(view=view):
                self.assertEqual(report_for("2022-23", view), edition)
                sources = select_sources(self.catalog, "2022-23", view, self.heading)
                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0].report, edition)
                loaded = read_sources(sources)
                with sources[0].path.open(encoding="utf-8-sig", newline="") as stream:
                    original = list(csv.DictReader(stream))
                self.assertEqual(loaded.to_dict("records"), original)

    def test_unavailable_revision_does_not_fall_back(self):
        self.assertEqual(select_sources(self.catalog, "2024-25", "Revision 2"), [])
        self.assertEqual(select_sources(self.catalog, "2023-24", "Revision 2"), [])
        self.assertEqual(report_for("2023-24", "Revision 1"), "24-25")


    def test_ordinary_rows_exclude_overall_totals(self):
        data = read_sources(select_sources(self.catalog, "2022-23", "Revision 2", self.heading))
        ordinary = filter_records(data)
        self.assertFalse(ordinary["dc"].isin(OVERALL_NAMES).any())
        self.assertFalse((ordinary["row_type"] == "grand_total").any())
        result = filter_records(data, state="Kerala", row_type="Utility", sector="Public")
        self.assertFalse(result.empty)
        self.assertTrue((result["st"] == "Kerala").all())
        self.assertTrue((result["row_type"] == "utility").all())
        self.assertTrue((result["sector"] == "Public").all())

    def test_totals_choose_the_source_total_without_summing(self):
        data = read_sources(select_sources(self.catalog, "2022-23", "Revision 2", self.heading))
        for sector, name in [("All", "Grand Total"), ("Public", "State Sector"), ("Private", "Private Sector")]:
            with self.subTest(sector=sector):
                expected = data.loc[data["dc"] == name].reset_index(drop=True)
                actual = filter_records(data, state="Kerala", row_type="Utility", sector=sector, totals_only=True)
                pd.testing.assert_frame_equal(actual, expected)
                self.assertFalse(actual.empty)

    def test_unknown_ownership_is_not_assigned_to_public_or_private(self):
        data = read_sources(select_sources(self.catalog, "2018-19", "Preliminary", self.heading))
        self.assertFalse(filter_records(data).empty)
        self.assertTrue(filter_records(data, sector="Public").empty)
        self.assertTrue(filter_records(data, sector="Private", totals_only=True).empty)
        self.assertFalse(filter_records(data, totals_only=True).empty)
        self.assertFalse(set(state_names(data)) & NON_STATES)

    def test_all_indexed_flat_files_and_index_are_byte_identical(self):
        baseline_path = DASHBOARD / "source-integrity.json"
        if not baseline_path.is_file():
            self.skipTest("Local extraction integrity baseline is not part of the cloud checkout")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        for relative, expected in baseline.items():
            path = DASHBOARD.parent / relative
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, relative)


class InterfaceTests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def test_flat_columns_and_revision_filter_in_display(self):
        app = self.app()
        app.multiselect(key="year").set_value(["2022-23"]).run()
        app.multiselect(key="view").set_value(["Revision 2"]).run()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        app.multiselect(key="state").set_value(["Kerala"]).run()
        app.multiselect(key="row_type").set_value(["Utility"]).run()
        app.multiselect(key="sector").set_value(["Public"]).run()
        self.assertFalse(app.exception)
        display = app.dataframe[0].value
        self.assertEqual(list(display.columns), FIELDS)
        self.assertEqual(set(display["yod"]), {"2022-23"})
        self.assertEqual(set(display["st"]), {"Kerala"})
        self.assertEqual(set(display["row_type"]), {"utility"})
        self.assertEqual(set(display["sector"]), {"Public"})
        self.assertTrue(any("Source report: 2024-25" in c.value for c in app.caption))

    def test_requested_title_caption_removal_and_first_annexure(self):
        app = self.app()
        self.assertEqual(app.title[0].value, "PFC-Report on discomms-Dashboard")
        self.assertFalse(any("does not edit or save" in c.value for c in app.caption))
        self.assertEqual(app.multiselect(key="major_heads").options[0], "Revenue details")
        self.assertEqual(app.dataframe[0].value.iloc[0]["ann"], "1.1")

    def test_totals_control_removed_and_old_session_cannot_enable_it(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30)
        app.session_state["totals_only"] = True
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(any(widget.key == "totals_only" for widget in app.checkbox))
        self.assertFalse(app.multiselect(key="state").disabled)
        self.assertFalse(app.multiselect(key="row_type").disabled)
        for categories in (["Public"], ["Private"], ["Public", "Private"]):
            app.multiselect(key="sector").set_value(categories).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.dataframe[0].value["dc"].isin(OVERALL_NAMES).any())
            self.assertFalse((app.dataframe[0].value["row_type"] == "grand_total").any())

    def test_unavailable_revision_has_message_and_no_stale_results(self):
        app = self.app()
        app.multiselect(key="year").set_value(["2024-25"]).run()
        app.multiselect(key="view").set_value(["Revision 2"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        self.assertTrue(any("No other revision has been substituted" in item.value for item in app.info))

    def test_pagination_resets_when_filters_change(self):
        app = self.app()
        app.number_input(key="page").set_value(2).run()
        self.assertEqual(app.number_input(key="page").value, 2)
        app.multiselect(key="row_type").set_value(["Utility"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key="page").value, 1)


if __name__ == "__main__":
    unittest.main()
