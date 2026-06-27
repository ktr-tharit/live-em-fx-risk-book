"""
pnl_calc.py
-----------
Calculates daily P&L for the positions logged in positions.csv,
using actual historical FX rate changes from fx_rates.csv.

Direction convention:
    LONG_USD  -> profit when USDXXX rises (local currency weakens vs USD)
    SHORT_USD -> profit when USDXXX falls (local currency strengthens vs USD)

P&L formula (USD terms, approximated using % change in the rate):
    daily_pnl_usd = notional_usd * direction_sign * pct_change_in_rate

This is an approximation (ignores convexity from converting local P&L back to
USD at the new rate), which is fine for a risk-monitoring project at this
scale. Note the approximation in any write-up so it's clear it's a deliberate
simplification, not an oversight.

Usage:
    python pnl/pnl_calc.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import FX_RATES_FILE, POSITIONS_FILE, DATA_DIR

DIRECTION_SIGN = {
    "LONG_USD": 1,
    "SHORT_USD": -1,
    "FLAT": 0,
}

OUTPUT_FILE = DATA_DIR / "daily_pnl.csv"


def load_fx_rates() -> pd.DataFrame:
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    df = df.sort_values(["pair", "date"])
    df["pct_change"] = df.groupby("pair")["rate"].pct_change()
    return df


def load_positions() -> pd.DataFrame:
    df = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])
    df["direction_sign"] = df["direction"].map(DIRECTION_SIGN)
    if df["direction_sign"].isna().any():
        bad = df[df["direction_sign"].isna()]
        raise ValueError(f"Unrecognised direction value(s) in positions.csv:\n{bad}")
    return df


def calc_pnl_for_position(position_row: pd.Series, fx_rates: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily P&L for a single position while it is open.

    end_date is optional in positions.csv. Blank means the position is still
    open and should use all available subsequent FX history.
    """
    pair = position_row["pair"]
    pair_rates = fx_rates[fx_rates["pair"] == pair].copy()
    pair_rates = pair_rates[pair_rates["date"] >= position_row["as_of_date"]]
    if pd.notna(position_row["end_date"]):
        pair_rates = pair_rates[pair_rates["date"] <= position_row["end_date"]]

    pair_rates["notional_usd"] = position_row["notional_usd"]
    pair_rates["direction"] = position_row["direction"]
    pair_rates["view_tag"] = position_row["view_tag"]
    pair_rates["daily_pnl_usd"] = (
        pair_rates["notional_usd"]
        * position_row["direction_sign"]
        * pair_rates["pct_change"]
    )

    return pair_rates[["date", "pair", "direction", "view_tag", "notional_usd",
                        "pct_change", "daily_pnl_usd"]]


def main():
    fx_rates = load_fx_rates()
    positions = load_positions()

    all_pnl = []
    for _, pos in positions.iterrows():
        pnl_df = calc_pnl_for_position(pos, fx_rates)
        all_pnl.append(pnl_df)

    result = pd.concat(all_pnl, ignore_index=True)
    result = result.dropna(subset=["daily_pnl_usd"])  # first day of each pair has no pct_change
    result = result.sort_values(["pair", "date"])

    result.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved daily P&L to {OUTPUT_FILE}")
    print(f"\nSummary by pair:")
    print(result.groupby("pair")["daily_pnl_usd"].sum().round(0))

    portfolio_daily = result.groupby("date")["daily_pnl_usd"].sum()
    print(f"\nLatest 5 days of total portfolio P&L:")
    print(portfolio_daily.tail(5).round(0))


if __name__ == "__main__":
    main()
