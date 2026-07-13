import unittest

import pandas as pd

from pnl.pnl_calc import calc_pnl_for_position


class PnlLogicTest(unittest.TestCase):
    def test_entry_day_is_excluded_and_close_day_is_included(self):
        rates = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "pair": ["USDTHB"] * 3,
            "previous_rate": [None, 35.0, 36.0],
            "rate": [35.0, 36.0, 34.0],
            "spot_return": [None, 36 / 35 - 1, 34 / 36 - 1],
            "usd_pnl_return": [None, 1 - 35 / 36, 1 - 36 / 34],
        })
        position = pd.Series({
            "position_id": "POS-TEST", "as_of_date": pd.Timestamp("2026-01-01"),
            "end_date": pd.Timestamp("2026-01-02"), "pair": "USDTHB",
            "direction": "LONG_USD", "direction_sign": 1, "notional_usd": 100.0,
            "view_tag": "test",
        })
        result = calc_pnl_for_position(position, rates)
        self.assertEqual(result["date"].tolist(), [pd.Timestamp("2026-01-02")])
        self.assertAlmostEqual(result.iloc[0]["daily_pnl_usd"], 100 * (1 - 35 / 36))

    def test_short_usd_reverses_the_return(self):
        rates = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "pair": ["USDTHB"] * 2, "previous_rate": [None, 35.0],
            "rate": [35.0, 36.0], "spot_return": [None, 36 / 35 - 1],
            "usd_pnl_return": [None, 1 - 35 / 36],
        })
        position = pd.Series({
            "position_id": "POS-TEST", "as_of_date": pd.Timestamp("2026-01-01"),
            "end_date": pd.NaT, "pair": "USDTHB", "direction": "SHORT_USD",
            "direction_sign": -1, "notional_usd": 100.0, "view_tag": "test",
        })
        result = calc_pnl_for_position(position, rates)
        self.assertLess(result.iloc[0]["daily_pnl_usd"], 0)


if __name__ == "__main__":
    unittest.main()
