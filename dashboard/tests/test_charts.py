"""Chart correctness and UI coverage, including source preservation."""
import json
from pathlib import Path
import sys
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
from charts import build_chart, measure_options, prepare_chart_data
from data_access import FIELDS, read_catalog, read_sources, select_sources, filter_records


class ChartTests(unittest.TestCase):
    def frame(self, numbers):
        rows = []
        for year, number in enumerate(numbers, 2018):
            row = dict.fromkeys(FIELDS, "")
            row.update(header="Revenue Details", label="Revenue_from_Operations", unit="Rs crore",
                       row_type="utility", st="Delhi", dc="BRPL", sector="Private", yop="Feb 2026",
                       yod=f"{year}-{(year + 1) % 100:02d}", number=number)
            rows.append(row)
        return pd.DataFrame(rows)

    def test_numeric_conversion_preserves_strings_zero_negatives_and_missing_gaps(self):
        original = self.frame(["1,234.50", "(25.50)", "", "−2", "0", "-", "NaN", "inf", "N/A"])
        before = original.copy(deep=True)
        data, omitted = prepare_chart_data(original, measure_options(original)[0])
        self.assertEqual(omitted, 5)
        self.assertEqual(data.value.tolist(), [1234.5, -25.5, -2., 0.])
        self.assertEqual(data.number.tolist(), ["1,234.50", "(25.50)", "−2", "0"])
        self.assertEqual(data.segment.iloc[0], data.segment.iloc[1])
        self.assertNotEqual(data.segment.iloc[1], data.segment.iloc[2])
        pd.testing.assert_frame_equal(original, before)

    def test_measure_identity_separates_tables_units_and_aggregation_levels(self):
        original = self.frame(["1", "2", "3", "4"])
        original.loc[1, "unit"] = "Rs/kWh"
        original.loc[2, "row_type"] = "state_aggregate"
        original.loc[3, "header"] = "Revenue Structure"
        options = measure_options(original)
        self.assertEqual(len(options), 4)
        for measure in options:
            data, omitted = prepare_chart_data(original, measure)
            self.assertEqual(len(data), 1)
            self.assertEqual(omitted, 0)

    def test_publications_are_not_merged_or_summed_and_specs_validate(self):
        original = self.frame(["12", "13", "14", "15"])
        original.loc[2:, "yop"] = "Feb 2025"
        original.loc[2:, "yod"] = original.loc[:1, "yod"].to_list()
        data, _ = prepare_chart_data(original, measure_options(original)[0])
        self.assertEqual(len(data), 4)
        self.assertEqual(data.groupby("yop").segment.nunique().to_list(), [1, 1])
        self.assertEqual(data.segment.nunique(), 2)
        for kind in ("Comparison (bars)", "Trend (lines)"):
            spec = build_chart(data, kind, "Rs crore").to_dict(validate=True)
            encoded = json.dumps(spec)
            self.assertNotIn('"aggregate"', encoded)
            self.assertNotIn('"transform"', encoded)
            self.assertEqual(spec["encoding"]["tooltip"][1]["field"], "number")
            channel = "color" if kind == "Comparison (bars)" else "strokeDash"
            self.assertEqual(spec["encoding"][channel]["field"], "yop")

    def test_real_filtered_source_observations_match_chart_values(self):
        source = read_sources(select_sources(read_catalog(), ["2022-23", "2023-24"],
                                            ["Preliminary", "Revision 1"], "Revenue details"))
        source = filter_records(source, "Delhi", "Utility", "Private")
        measure = ("Revenue Details", "Revenue_from_Operations", "Rs crore", "utility")
        data, omitted = prepare_chart_data(source, measure)
        expected = source[source.label == measure[1]]
        self.assertEqual(len(data), len(expected))
        self.assertEqual(omitted, 0)
        self.assertEqual(sorted(data.number), sorted(expected.number))
        self.assertEqual(set(data.yop), {"Apr 2024", "Feb 2025", "Feb 2026"})

    def test_graph_switch_filters_pagination_and_clear_all(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30).run()
        app.multiselect(key="major_heads").set_value(["Revenue details", "Revenue Structure"]).run()
        app.multiselect(key="minor_heads").set_value(["Revenue_from_Operations"]).run()
        app.number_input(key="page").set_value(2).run()
        app.radio(key="output_mode").set_value("Graphs").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)
        self.assertEqual(len(app.selectbox(key="graph_measure").options), 4)
        # A graph covers the whole filtered measure, even from table page 2.
        self.assertTrue(any("independent of table pagination" in c.value for c in app.caption))
        app.multiselect(key="year").set_value(["2022-23", "2023-24", "2024-25"]).run()
        app.selectbox(key="graph_type").set_value("Trend (lines)").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)
        # A measure whose table is removed must be replaced by a valid choice.
        app.selectbox(key="graph_measure").set_value(
            ("Revenue Structure", "Revenue_from_Operations", "Rs/kWh", "utility")).run()
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="graph_measure").value[0], "Revenue Details")
        app.button(key="clear_all").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("vega_lite_chart")), 0)
        self.assertTrue(all(widget.value == (["Latest available"] if widget.key == "view" else [])
                            for widget in app.multiselect))


if __name__ == "__main__":
    unittest.main()
