import unittest

import pandas as pd

from macro.trade_thesis import THESIS_COLUMNS, next_thesis_id, validate_trade_theses


class TradeThesisTest(unittest.TestCase):
    def test_valid_schema_and_next_id(self):
        df = pd.DataFrame([{
            "thesis_id": "THESIS-0007", "as_of_date": "2026-07-15",
            "pair": "USDTHB", "direction": "LONG_USD",
            "drivers": "Fed rate path;Local CB policy", "custom_driver": "",
            "thesis": "THB weakens as the policy differential widens.",
            "conviction": "medium",
        }], columns=THESIS_COLUMNS)
        validate_trade_theses(df)
        self.assertEqual(next_thesis_id(df), "THESIS-0008")

    def test_unknown_driver_is_rejected(self):
        df = pd.DataFrame([{
            "thesis_id": "THESIS-0001", "as_of_date": "2026-07-15",
            "pair": "USDTHB", "direction": "LONG_USD",
            "drivers": "Unknown driver", "custom_driver": "",
            "thesis": "Test", "conviction": "low",
        }], columns=THESIS_COLUMNS)
        with self.assertRaisesRegex(ValueError, "unknown driver"):
            validate_trade_theses(df)


if __name__ == "__main__":
    unittest.main()
