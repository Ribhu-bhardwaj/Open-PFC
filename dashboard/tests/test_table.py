"""Wide-table presentation without aggregation, rounding or source edits."""
import json
from pathlib import Path
import sys
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
from data_access import FIELDS, label_columns


class TableTests(unittest.TestCase):
    def rows(self):
        base = dict.fromkeys(FIELDS, "")
        base.update(yop="Feb 2026", yod="2024-25", ann="1.1", header="Revenue Details",
                    st="Delhi", dc="BRPL", row_type="utility", sector="Private", pg="1", unit="Rs crore")
        return pd.DataFrame([
            dict(base, label="Revenue", number="1,234.00"),
            dict(base, label="Subsidy", number="-2.50", pg="2", unit="Rs/kWh"),
            dict(base, label="Revenue", number="0", dc="BYPL"),
            dict(base, label="Revenue", number="999.0", yop="Feb 2025"),
            dict(base, label="Revenue", number="888.0", yod="2023-24"),
            dict(base, label="Revenue", number="777.0", ann="1.1(a)", header="Revenue Structure"),
            dict(base, label="Revenue", number="666.0", sector="Public"),
            dict(base, label="Revenue", number="555.0", st="Another state"),
            dict(base, label="Revenue", number="444.0", row_type="state_aggregate"),
        ])

    def test_values_share_entity_rows_and_keep_selected_column_order(self):
        rows = self.rows()
        before = rows.copy(deep=True)
        actual = label_columns(rows, ["Subsidy", "Revenue", "Unavailable"])
        self.assertEqual(list(actual.columns), ["dc", "Subsidy", "Revenue", "Unavailable"])
        self.assertEqual(actual.drop(columns="dc").values.tolist(), [
            ["-2.50", "1,234.00", ""], ["", "0", ""], ["", "999.0", ""],
            ["", "888.0", ""], ["", "777.0", ""], ["", "666.0", ""],
            ["", "555.0", ""], ["", "444.0", ""],
        ])
        self.assertEqual(actual.dc.tolist(), ["BRPL", "BYPL", "BRPL", "BRPL", "BRPL", "BRPL", "BRPL", "BRPL"])
        pd.testing.assert_frame_equal(rows, before)

    def test_duplicate_observations_are_not_overwritten_or_aggregated(self):
        rows = pd.concat([self.rows().iloc[:2], self.rows().iloc[:1]], ignore_index=True)
        actual = label_columns(rows, ["Revenue", "Subsidy"])
        self.assertEqual(actual.values.tolist(), [["BRPL", "1,234.00", "-2.50"], ["BRPL", "1,234.00", ""]])
        self.assertTrue(label_columns(rows, []).empty)

    def test_ui_columns_alignment_and_pagination_use_reshaped_rows(self):
        app = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=30).run()
        app.multiselect(key="minor_heads").set_value(
            ["Revenue_from_Operations", "Tariff_Subsidy_Billed"]).run()
        self.assertFalse(app.exception)
        frame = app.dataframe[0].value
        self.assertEqual(list(frame.columns), ["dc", "Revenue_from_Operations", "Tariff_Subsidy_Billed"])
        self.assertEqual(frame.iloc[0].tolist(), ["Andaman & Nicobar Islands", "307.0", "790.0"])
        config = json.loads(app.dataframe[0].proto.columns)
        self.assertEqual(config["dc"]["label"], "Discomm")
        self.assertEqual(config["dc"]["alignment"], "left")
        for label in frame.columns[1:]:
            self.assertEqual(config[label]["alignment"], "right")
        app.multiselect(key="major_heads").set_value(["Revenue details"]).run()
        app.multiselect(key="state").set_value(["Delhi"]).run()
        self.assertFalse(app.exception)
        # Two category aggregates and four utilities, each with two measures.
        self.assertEqual(len(app.dataframe[0].value), 6)
        self.assertEqual(set(app.dataframe[0].value.dc), {"Delhi", "NDMC", "BRPL", "BYPL", "TPDDL"})
        self.assertTrue(any("Rows 1-6 of 6" in caption.value for caption in app.caption))
        self.assertEqual(app.number_input(key="page").max, 1)


if __name__ == "__main__":
    unittest.main()
