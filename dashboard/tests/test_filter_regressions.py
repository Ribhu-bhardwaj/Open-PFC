"""Regression coverage for deployment reloads and dependent multi-select filters."""
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit import config
from streamlit.runtime.pages_manager import PagesManager
from streamlit.testing.v1 import AppTest
from streamlit.watcher import local_sources_watcher

DASHBOARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
from data_access import (label_columns, FIELDS, LATEST_VIEW, filter_records, filter_discomms, heading_options, read_catalog,
                         read_sources, select_sources, selected_report_pairs)


class DeploymentTests(unittest.TestCase):
    def test_changed_imported_helper_is_reloaded_with_dashboard_configuration(self):
        """A running process must see a new helper API after a code update."""
        settings = tomllib.loads((DASHBOARD / ".streamlit/config.toml").read_text())
        get_option = config.get_option
        watcher_type = settings.get("server", {}).get("fileWatcherType", "auto")
        def configured_option(name):
            return watcher_type if name == "server.fileWatcherType" else get_option(name)

        # Streamlit deliberately ignores dot-directories, so the probe must be
        # in a normal source directory, just like the deployed helper module.
        with tempfile.TemporaryDirectory(prefix="reload-check-", dir=DASHBOARD) as directory:
            root = Path(directory)
            entry = root / "app.py"
            entry.write_text("import dashboard_reload_probe\n", encoding="utf-8")
            helper = root / "dashboard_reload_probe.py"
            helper.write_text("def old_api():\n    return 1\n", encoding="utf-8")
            sys.path.insert(0, directory)
            watcher = None
            try:
                old_module = importlib.import_module("dashboard_reload_probe")
                self.assertFalse(hasattr(old_module, "head_groups"))
                with patch.object(config, "get_option", side_effect=configured_option), patch.object(
                        local_sources_watcher, "PathWatcher", None):
                    watcher = local_sources_watcher.LocalSourcesWatcher(PagesManager(str(entry)))
                    changed = threading.Event()
                    watcher.register_file_change_callback(
                        lambda path: changed.set() if Path(path).resolve() == helper.resolve() else None)
                    watcher.update_watched_modules()
                    helper.write_text('def head_groups():\n    return ["Revenue details"]\n', encoding="utf-8")
                    self.assertTrue(changed.wait(5), "Imported helper changes were not detected")
                    watcher.on_script_run()
                    importlib.invalidate_caches()
                    updated = importlib.import_module("dashboard_reload_probe")
                    self.assertEqual(updated.head_groups(), ["Revenue details"])
            finally:
                if watcher is not None:
                    watcher.close()
                sys.modules.pop("dashboard_reload_probe", None)
                sys.path.remove(directory)


class FilterRegressionTests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30).run()
        self.assert_clean(app)
        return app

    def assert_clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertFalse(app.warning, [w.value for w in app.warning])

    def assert_source_rows(self, app):
        selected = lambda key: app.multiselect(key=key).value
        sources = select_sources(read_catalog(), selected("year"), selected("view"), selected("major_heads"))
        category = "All" if set(selected("sector")) == {"Public", "Private"} else selected("sector")
        expected = filter_records(read_sources(sources), selected("state"), selected("row_type"), category)
        if "Utility" in selected("row_type"):
            expected = filter_discomms(expected, selected("discomms"))
        expected = expected.loc[expected.label.isin(selected("minor_heads"))].reset_index(drop=True)
        pd.testing.assert_frame_equal(app.dataframe[0].value, label_columns(expected, app.multiselect(key="minor_heads").value).iloc[:100])

    def test_latest_available_resolves_each_data_year_independently(self):
        catalog = read_catalog()
        expected = {f"{year}-{(year + 1) % 100:02d}": f"{min(year + 2, 2024) % 100:02d}-{(min(year + 2, 2024) + 1) % 100:02d}"
                    for year in range(2016, 2025)}
        for year, report in expected.items():
            with self.subTest(year=year):
                sources = select_sources(catalog, year, LATEST_VIEW)
                self.assertTrue(sources)
                self.assertEqual({source.report for source in sources}, {report})
                self.assertEqual({source.year for source in sources}, {year})
        pairs = selected_report_pairs(catalog, ["2024-25", "2022-23", "2020-21"], [LATEST_VIEW])
        self.assertEqual(pairs, [("24-25", "2024-25"), ("24-25", "2022-23"), ("22-23", "2020-21")])
        self.assertEqual(select_sources(catalog, "2030-31", LATEST_VIEW), [])
        self.assertEqual(select_sources(catalog, [], LATEST_VIEW), [])
        self.assertEqual(select_sources(catalog, "2022-23", []), [])

    def test_latest_available_uses_actual_catalog_and_deduplicates_views(self):
        catalog = read_catalog()
        reduced = [source for source in catalog if source.report != "24-25"]
        self.assertEqual(selected_report_pairs(reduced, "2022-23", LATEST_VIEW), [("23-24", "2022-23")])
        latest = select_sources(catalog, "2022-23", LATEST_VIEW)
        self.assertEqual(select_sources(catalog, "2022-23", [LATEST_VIEW, "Revision 2"]), latest)
        combined = select_sources(catalog, "2022-23", [LATEST_VIEW, "Preliminary"])
        self.assertEqual({source.report for source in combined}, {"22-23", "24-25"})
        self.assertEqual(len(combined), len({source.path for source in combined}))
        # Consumer tables exist in 2023-24 but not the newest 2024-25 report.
        heading = "Consumer Category-wise Revenue per Unit"
        self.assertTrue(select_sources(catalog, "2022-23", "Revision 1", heading))
        self.assertEqual(select_sources(catalog, "2022-23", LATEST_VIEW, heading), [])

    def test_latest_available_display_matches_revision_two_and_survives_clear(self):
        app = self.app()
        self.assertIn(LATEST_VIEW, app.multiselect(key="view").options)
        self.assertEqual(app.multiselect(key="view").value, [LATEST_VIEW])
        app.multiselect(key="year").set_value(["2022-23"]).run()
        app.multiselect(key="view").set_value(["Revision 2"]).run()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        app.multiselect(key="state").set_value(["Kerala"]).run()
        expected = app.dataframe[0].value.copy()
        app.multiselect(key="view").set_value([LATEST_VIEW]).run()
        self.assert_clean(app)
        pd.testing.assert_frame_equal(app.dataframe[0].value, expected)
        self.assertTrue(any("Source report: 2024-25" in caption.value for caption in app.caption))
        app.multiselect(key="view").set_value([LATEST_VIEW, "Revision 2"]).run()
        self.assert_clean(app)
        pd.testing.assert_frame_equal(app.dataframe[0].value, expected)
        app.button(key="clear_all").click().run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="view").value, [])
        self.assertEqual(len(app.dataframe), 0)

    def test_filter_order_native_select_all_and_plain_head_labels(self):
        app = self.app()
        self.assertEqual([widget.label for widget in app.multiselect[:6]],
                         ["Select year", "Category", "Sector", "State (st)", "Major Heads", "Minor Heads"])
        for widget in app.multiselect:
            self.assertNotIn("All", widget.options)
        majors = app.multiselect(key="major_heads")
        self.assertEqual(majors.options[0], "Revenue details")
        self.assertIn("Revenue Structure", majors.options)
        self.assertIn("Revenue Structure on Energy Sold basis", majors.options)
        self.assertIn("Revenue_from_Operations", app.multiselect(key="minor_heads").value)
        self.assertEqual(list(app.dataframe[0].value.columns), app.multiselect(key="minor_heads").value)

    def test_minor_heads_select_labels_across_tables_and_prune_stale_choices(self):
        app = self.app()
        app.multiselect(key="major_heads").set_value(["Revenue details", "Revenue Structure"]).run()
        app.multiselect(key="state").set_value(["Kerala"]).run()
        labels = ["Revenue_from_Operations", "Tariff_Subsidy_Billed"]
        app.multiselect(key="minor_heads").set_value(labels).run()
        self.assert_clean(app)
        sources = select_sources(read_catalog(), "2024-25", LATEST_VIEW,
                                 ["Revenue details", "Revenue Structure"])
        expected = filter_records(read_sources(sources), ["Kerala"])
        expected = expected.loc[expected.label.isin(labels)].reset_index(drop=True)
        pd.testing.assert_frame_equal(app.dataframe[0].value, label_columns(expected, app.multiselect(key="minor_heads").value))
        app.multiselect(key="major_heads").set_value(["Expense Details"]).run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="minor_heads").value, [])
        self.assertEqual(len(app.dataframe), 0)
        self.assertIn("Cost_of_Power_Including_Own_Generation", app.multiselect(key="minor_heads").options)

    def test_old_minor_table_selections_migrate_to_major_heads(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30)
        app.session_state["major_heads"] = ["Revenue details"]
        app.session_state["minor_heads"] = ["Revenue Structure"]
        app.run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="major_heads").value,
                         ["Revenue details", "Revenue Structure"])
        self.assertIn("Revenue_from_Operations", app.multiselect(key="minor_heads").value)

    def test_multiple_years_views_states_and_heads_match_source_rows(self):
        app = self.app()
        selections = {"year": ["2022-23", "2023-24"], "view": ["Preliminary", "Revision 1"],
                      "major_heads": ["Revenue details", "Expense Details", "Revenue Structure", "Cost Structure"],
                      "state": ["Kerala", "Goa"], "row_type": ["Utility"], "sector": ["Public"]}
        for key, values in selections.items():
            app.multiselect(key=key).set_value(values)
        app.run()
        self.assert_clean(app)
        sources = select_sources(read_catalog(), selections["year"], selections["view"],
                                 selections["major_heads"])
        expected = filter_records(read_sources(sources), selections["state"], ["Utility"], ["Public"])
        pd.testing.assert_frame_equal(app.dataframe[0].value, label_columns(expected, app.multiselect(key="minor_heads").value).iloc[:100])

    def test_clearing_filters_produces_no_rows_and_select_all_restores_them(self):
        app = self.app()
        for key in ("sector", "row_type", "state", "major_heads", "minor_heads", "year", "view"):
            with self.subTest(key=key):
                previous = app.multiselect(key=key).value
                app.multiselect(key=key).set_value([]).run()
                self.assert_clean(app)
                self.assertEqual(len(app.dataframe), 0)
                app.multiselect(key=key).set_value(previous).run()
                self.assert_clean(app)
                self.assertEqual(len(app.dataframe), 1)

    def test_unavailable_revision_recovers_all_selected_measures(self):
        app = self.app()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        previous = app.multiselect(key="minor_heads").value
        app.multiselect(key="view").set_value(["Revision 2"]).run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="minor_heads").value, [])
        self.assertEqual(len(app.dataframe), 0)
        app.multiselect(key="view").set_value(["Preliminary"]).run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="minor_heads").value, previous)
        self.assertEqual(len(app.dataframe), 1)

    def test_clear_all_empties_every_filter_and_stays_empty_on_rerun(self):
        app = self.app()
        app.number_input(key="page").set_value(2).run()
        app.button(key="clear_all").click().run()
        for _ in range(2):
            self.assert_clean(app)
            for widget in app.multiselect:
                self.assertEqual(widget.value, [], widget.label)
            self.assertEqual(len(app.dataframe), 0)
            app.run()
        # Rebuilding the year/head choices must not silently select states.
        for key, value in {"year": ["2024-25"], "view": ["Preliminary"],
                           "major_heads": ["Revenue details"]}.items():
            app.multiselect(key=key).set_value(value).run()
        self.assertEqual(app.multiselect(key="state").value, [])
        self.assertEqual(app.multiselect(key="sector").value, [])
        self.assertEqual(app.multiselect(key="row_type").value, [])
        for key, value in {"state": ["Kerala"], "sector": ["Public"], "row_type": ["Utility"]}.items():
            app.multiselect(key=key).set_value(value).run()
        self.assertEqual(app.multiselect(key="discomms").value, [])
        self.assertEqual(app.multiselect(key="minor_heads").value, [])
        app.multiselect(key="minor_heads").set_value(["Revenue_from_Operations"]).run()
        app.multiselect(key="discomms").set_value([("Kerala", "Public", "KSEBL")]).run()
        self.assert_clean(app)
        self.assertEqual(len(app.dataframe), 1)
        self.assertEqual(app.number_input(key="page").value, 1)
        self.assert_source_rows(app)

    def test_discomms_follow_state_category_and_filter_selected_utilities(self):
        app = self.app()
        for key, value in {"major_heads": ["Revenue details"], "state": ["Delhi"],
                           "row_type": ["Utility"], "sector": ["Private"]}.items():
            app.multiselect(key=key).set_value(value).run()
        self.assertEqual(set(app.multiselect(key="discomms").value),
                         {("Delhi", "Private", name) for name in ("BRPL", "BYPL", "TPDDL")})
        app.multiselect(key="discomms").set_value([("Delhi", "Private", "BRPL"),
                                                   ("Delhi", "Private", "TPDDL")]).run()
        self.assert_clean(app)
        self.assert_source_rows(app)
        app.multiselect(key="sector").set_value(["Public"]).run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key="discomms").options, ["NDMC (Delhi, Public)"])
        self.assertEqual(app.multiselect(key="discomms").value, [])
        self.assertEqual(len(app.dataframe), 0)
        app.multiselect(key="discomms").set_value([("Delhi", "Public", "NDMC")]).run()
        self.assert_source_rows(app)

    def test_discomms_leave_state_aggregates_unchanged(self):
        app = self.app()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        app.multiselect(key="state").set_value(["Kerala", "Delhi"]).run()
        app.multiselect(key="sector").set_value(["Public"]).run()
        app.multiselect(key="discomms").set_value([("Kerala", "Public", "KSEBL")]).run()
        self.assert_clean(app)
        self.assert_source_rows(app)
        app.multiselect(key="row_type").set_value(["State aggregate"]).run()
        self.assertTrue(app.multiselect(key="discomms").disabled)
        self.assert_source_rows(app)
        self.assert_clean(app)

    def test_discomms_respect_years_views_and_heads(self):
        app = self.app()
        app.multiselect(key="year").set_value(["2022-23", "2023-24"]).run()
        app.multiselect(key="view").set_value(["Preliminary", "Revision 1"]).run()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        app.multiselect(key="major_heads").set_value(["Revenue details", "Revenue Structure"]).run()
        app.multiselect(key="state").set_value(["Delhi", "Gujarat"]).run()
        app.multiselect(key="sector").set_value(["Private"]).run()
        app.multiselect(key="row_type").set_value(["Utility"]).run()
        app.multiselect(key="discomms").set_value([("Delhi", "Private", "BRPL"),
                                                   ("Gujarat", "Private", "Torrent Power Surat")]).run()
        self.assert_clean(app)
        sources = select_sources(read_catalog(), ["2022-23", "2023-24"], ["Preliminary", "Revision 1"],
                                 ["Revenue details", "Revenue Structure"])
        expected = filter_records(read_sources(sources), ["Delhi", "Gujarat"], ["Utility"], ["Private"])
        expected = expected.loc[expected.dc.isin(["BRPL", "Torrent Power Surat"])].reset_index(drop=True)
        pd.testing.assert_frame_equal(app.dataframe[0].value, label_columns(expected, app.multiselect(key="minor_heads").value).iloc[:100])

    def test_every_report_offers_all_tables_as_major_heads(self):
        catalog = read_catalog()
        for start in range(2018, 2025):
            year = f"{start}-{(start + 1) % 100:02d}"
            with self.subTest(year=year):
                options = heading_options(catalog, year, "Preliminary")
                sources = select_sources(catalog, year, "Preliminary")
                self.assertEqual(options[:len(sources)], [source.heading for source in sources])
                self.assertIn("Revenue Structure", options)
                self.assertIn("Cost Structure", options)


if __name__ == "__main__":
    unittest.main()
