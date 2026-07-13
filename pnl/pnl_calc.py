import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_DIR, FX_RATES_FILE, POSITIONS_FILE

DIRECTION_SIGN = {"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0}
OUTPUT_FILE = DATA_DIR / "daily_pnl.csv"


def load_fx_rates() -> pd.DataFrame:
    """Return USDXXX closes and the exact one-day USD P&L return.

    A USD notional translated back from local currency earns
    (spot_t - spot_t-1) / spot_t, not the usual spot percentage change.
    """
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    df = df.sort_values(["pair", "date"])
    previous_rate = df.groupby("pair")["rate"].shift(1)
    df["previous_rate"] = previous_rate
    df["spot_return"] = df["rate"] / previous_rate - 1
    df["usd_pnl_return"] = 1 - previous_rate / df["rate"]
    return df


def load_positions() -> pd.DataFrame:
    df = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])
    required = {"position_id", "as_of_date", "end_date", "pair", "direction", "notional_usd"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s) in positions.csv: {sorted(missing)}")
    if df["position_id"].isna().any() or df["position_id"].duplicated().any():
        raise ValueError("position_id must be present and unique for every position")
    df["direction_sign"] = df["direction"].map(DIRECTION_SIGN)
    if df["direction_sign"].isna().any():
        bad = df.loc[df["direction_sign"].isna(), "direction"].unique()
        raise ValueError(f"Unrecognised direction value(s): {bad}")
    return df


def calc_pnl_for_position(position: pd.Series, fx_rates: pd.DataFrame) -> pd.DataFrame:
    """Calculate close-to-close P&L after open, through the close date.

    as_of_date is treated as the entry close, so that day's move happened
    before the order existed. end_date is treated as the exit close, so its
    close-to-close move belongs to the position.
    """
    rates = fx_rates.loc[
        (fx_rates["pair"] == position["pair"])
        & (fx_rates["date"] > position["as_of_date"])
    ].copy()
    if pd.notna(position["end_date"]):
        rates = rates.loc[rates["date"] <= position["end_date"]]

    rates["position_id"] = position["position_id"]
    rates["direction"] = position["direction"]
    rates["notional_usd"] = position["notional_usd"]
    rates["view_tag"] = position.get("view_tag", "")
    rates["daily_return"] = position["direction_sign"] * rates["usd_pnl_return"]
    rates["daily_pnl_usd"] = rates["notional_usd"] * rates["daily_return"]
    return rates[[
        "date", "position_id", "pair", "direction", "view_tag", "notional_usd",
        "previous_rate", "rate", "spot_return", "daily_return", "daily_pnl_usd",
    ]]


def calculate_daily_pnl(positions: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    frames = [calc_pnl_for_position(pos, fx_rates) for _, pos in positions.iterrows()]
    columns = [
        "date", "position_id", "pair", "direction", "view_tag", "notional_usd",
        "previous_rate", "rate", "spot_return", "daily_return", "daily_pnl_usd",
    ]
    if not frames:
        return pd.DataFrame(columns=columns)
    return (
        pd.concat(frames, ignore_index=True)
        .dropna(subset=["daily_return"])
        .sort_values(["date", "position_id"])
        .reset_index(drop=True)
    )


def main() -> None:
    result = calculate_daily_pnl(load_positions(), load_fx_rates())
    result.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(result)} position-day P&L rows to {OUTPUT_FILE}")
    if not result.empty:
        print("\nSummary by position:")
        print(result.groupby(["position_id", "pair"])["daily_pnl_usd"].sum().round(0))
        print("\nLatest 5 days of total portfolio P&L:")
        print(result.groupby("date")["daily_pnl_usd"].sum().tail(5).round(0))


if __name__ == "__main__":
    main()
