import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import FX_RATES_FILE, POSITIONS_FILE, STRESS_SCENARIOS_FILE, DATA_DIR

DIRECTION_SIGN = {"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0}
OUTPUT_FILE = DATA_DIR / "stress_test_results.csv"


def load_fx_rates() -> pd.DataFrame:
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    return df.pivot(index="date", columns="pair", values="rate").sort_index()


def load_current_positions(as_of_date: pd.Timestamp | None = None) -> pd.DataFrame:
    df = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])
    if as_of_date is None:
        as_of_date = pd.Timestamp.today().normalize()
    else:
        as_of_date = pd.Timestamp(as_of_date).normalize()

    df = df[
        (df["as_of_date"] <= as_of_date)
        & (df["end_date"].isna() | (df["end_date"] >= as_of_date))
    ].copy()
    df["direction_sign"] = df["direction"].map(DIRECTION_SIGN)
    df["signed_notional_usd"] = df["notional_usd"] * df["direction_sign"]
    return df.groupby("pair")["signed_notional_usd"].sum()


def cumulative_return_in_window(rates: pd.DataFrame, pair: str,
                                  start_date, end_date) -> float | None:
    if pair not in rates.columns:
        return None
    window = rates[pair].dropna()
    window = window[(window.index >= start_date) & (window.index <= end_date)]
    if len(window) < 2:
        return None
    return (window.iloc[-1] / window.iloc[0]) - 1


def main():
    rates = load_fx_rates()
    positions = load_current_positions()
    scenarios = pd.read_csv(STRESS_SCENARIOS_FILE, parse_dates=["start_date", "end_date"])

    results = []
    for _, scenario in scenarios.iterrows():
        row = {"scenario": scenario["scenario"], "description": scenario["description"]}
        portfolio_pnl = 0.0
        missing_pairs = []

        for pair, signed_notional in positions.items():
            cum_return = cumulative_return_in_window(
                rates, pair, scenario["start_date"], scenario["end_date"]
            )
            if cum_return is None:
                missing_pairs.append(pair)
                continue
            pair_pnl = signed_notional * cum_return
            row[f"{pair}_pnl_usd"] = round(pair_pnl, 0)
            portfolio_pnl += pair_pnl

        row["portfolio_pnl_usd"] = round(portfolio_pnl, 0)
        if missing_pairs:
            row["note"] = f"No data for: {', '.join(missing_pairs)}"
        results.append(row)

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUTPUT_FILE, index=False)

    print("=== Stress Test Results (current position book) ===\n")
    for _, row in result_df.iterrows():
        print(f"{row['scenario']}: portfolio P&L = ${row['portfolio_pnl_usd']:,.0f}")
        if "note" in row and pd.notna(row.get("note")):
            print(f"  ({row['note']})")
    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
