"""
backtest_var.py
----------------
Implements Basel-style VaR backtesting in two layers:

LAYER A — Historical constant-notional portfolio backtest:
    Uses a fixed hypothetical portfolio over the full FX history.
    Rolls VaR forward day by day using only prior data, then compares
    next-day hypothetical portfolio P&L against the VaR estimate.

LAYER B — Live portfolio backtest:
    Uses actual positions from positions.csv. For each date with active
    positions, it calculates portfolio VaR using only returns before that date,
    compares the actual portfolio P&L on that date, and flags exceptions.

Exception rule:
    exception = 1 if actual_pnl_usd < -var_usd

Traffic light zones for 99% VaR over 250 observations:
    0-4   exceptions -> GREEN
    5-9   exceptions -> YELLOW
    10+   exceptions -> RED

Usage:
    python risk/backtest_var.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config import (
    FX_RATES_FILE,
    POSITIONS_FILE,
    VAR_LOOKBACK_DAYS,
    BACKTEST_WINDOW_DAYS,
    TRAFFIC_LIGHT_ZONES,
    DATA_DIR,
)

DIRECTION_SIGN = {"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0}

CONFIDENCE = 0.99

OUTPUT_FILE_A = DATA_DIR / "backtest_layer_a_historical.csv"
OUTPUT_FILE_B = DATA_DIR / "backtest_layer_b_live.csv"


# Layer A: fixed hypothetical portfolio for methodology validation.
# Keep this simple and explicit.
LAYER_A_PORTFOLIO = {
    "USDTHB": 1_000_000,   # LONG_USD
    "USDZAR": -500_000,   # SHORT_USD
}


def classify_zone(num_exceptions: int) -> str:
    for zone, (low, high) in TRAFFIC_LIGHT_ZONES.items():
        if low <= num_exceptions <= high:
            return zone
    return "UNKNOWN"


def load_returns_wide() -> pd.DataFrame:
    """Load FX rates and convert to wide daily return table."""
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    wide = df.pivot(index="date", columns="pair", values="rate").sort_index()
    returns = wide.pct_change().dropna(how="all")
    return returns


def portfolio_pnl_from_returns(
    returns_window: pd.DataFrame,
    signed_positions: pd.Series,
) -> pd.Series:
    """
    Convert FX returns into portfolio P&L using signed USD notionals.

    signed_positions:
        +notional = LONG_USD
        -notional = SHORT_USD
    """
    common_pairs = [p for p in signed_positions.index if p in returns_window.columns]

    if not common_pairs:
        raise ValueError("No position pairs found in return data.")

    aligned_returns = returns_window[common_pairs]
    aligned_positions = signed_positions[common_pairs]

    return aligned_returns.mul(aligned_positions, axis=1).sum(axis=1)


def historical_var_from_pnl(
    pnl_distribution: pd.Series,
    confidence: float = CONFIDENCE,
) -> float:
    """
    Historical VaR from a P&L distribution.
    VaR is returned as a positive loss threshold.
    """
    loss_percentile = (1 - confidence) * 100
    var_usd = -np.percentile(pnl_distribution.dropna(), loss_percentile)
    return max(float(var_usd), 0.0)


def run_layer_a(returns: pd.DataFrame) -> pd.DataFrame:
    """
    Historical constant-notional portfolio backtest.

    This validates the VaR methodology using a fixed portfolio over history.
    It is available from day one because it does not rely on live project history.
    """
    signed_positions = pd.Series(LAYER_A_PORTFOLIO, dtype=float)

    common_pairs = [p for p in signed_positions.index if p in returns.columns]
    if not common_pairs:
        raise ValueError("Layer A portfolio pairs are not found in FX returns data.")

    signed_positions = signed_positions[common_pairs]
    returns = returns[common_pairs].dropna(how="all")

    records = []

    for i in range(VAR_LOOKBACK_DAYS, len(returns)):
        date = returns.index[i]

        # Only use data before the test date. No lookahead.
        history_window = returns.iloc[i - VAR_LOOKBACK_DAYS:i]
        actual_return_row = returns.iloc[[i]]

        hist_pnl = portfolio_pnl_from_returns(history_window, signed_positions)
        var_usd = historical_var_from_pnl(hist_pnl, CONFIDENCE)

        actual_pnl_usd = portfolio_pnl_from_returns(
            actual_return_row,
            signed_positions,
        ).iloc[0]

        exception = int(actual_pnl_usd < -var_usd)

        records.append({
            "date": date,
            "var_usd": var_usd,
            "actual_pnl_usd": actual_pnl_usd,
            "exception": exception,
        })

    result = pd.DataFrame(records)

    result["rolling_exceptions"] = (
        result["exception"]
        .rolling(BACKTEST_WINDOW_DAYS, min_periods=1)
        .sum()
    )

    result["traffic_light_zone"] = result["rolling_exceptions"].apply(
        lambda n: classify_zone(int(n))
    )

    return result


def load_positions() -> pd.DataFrame:
    """Load positions and calculate signed USD notionals."""
    positions = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])

    required_cols = {
        "as_of_date",
        "end_date",
        "pair",
        "direction",
        "notional_usd",
    }
    missing = required_cols - set(positions.columns)
    if missing:
        raise ValueError(f"Missing required columns in positions.csv: {missing}")

    positions["direction_sign"] = positions["direction"].map(DIRECTION_SIGN)

    if positions["direction_sign"].isna().any():
        bad = positions[positions["direction_sign"].isna()]
        raise ValueError(f"Unrecognised direction value(s):\n{bad}")

    positions["signed_notional_usd"] = (
        positions["notional_usd"] * positions["direction_sign"]
    )

    return positions


def active_positions_on_date(
    positions: pd.DataFrame,
    date: pd.Timestamp,
) -> pd.Series:
    """
    Return net signed USD notional by pair for positions active on a date.
    """
    active = positions[
        (positions["as_of_date"] <= date)
        & (positions["end_date"].isna() | (positions["end_date"] >= date))
    ].copy()

    if active.empty:
        return pd.Series(dtype=float)

    return active.groupby("pair")["signed_notional_usd"].sum()


def run_layer_b(returns: pd.DataFrame) -> pd.DataFrame:
    """
    Live portfolio-level backtest using actual positions.csv.

    For each date with active positions:
        1. Build active net portfolio for that date.
        2. Estimate VaR from prior return history only.
        3. Calculate actual portfolio P&L for that date.
        4. Flag exception if actual loss exceeds VaR.
    """
    positions = load_positions()
    records = []

    for date in returns.index:
        signed_positions = active_positions_on_date(positions, date)

        if signed_positions.empty:
            continue

        common_pairs = [p for p in signed_positions.index if p in returns.columns]
        if not common_pairs:
            continue

        signed_positions = signed_positions[common_pairs]

        history_window = returns.loc[returns.index < date, common_pairs].tail(
            VAR_LOOKBACK_DAYS
        )

        # Allow live tracking to start early, but avoid silly VaR estimates.
        if len(history_window) < 30:
            continue

        actual_return_row = returns.loc[[date], common_pairs]

        hist_pnl = portfolio_pnl_from_returns(history_window, signed_positions)
        var_usd = historical_var_from_pnl(hist_pnl, CONFIDENCE)

        actual_pnl_usd = portfolio_pnl_from_returns(
            actual_return_row,
            signed_positions,
        ).iloc[0]

        exception = int(actual_pnl_usd < -var_usd)

        records.append({
            "date": date,
            "var_usd": var_usd,
            "actual_pnl_usd": actual_pnl_usd,
            "exception": exception,
            "active_pairs": ",".join(common_pairs),
            "gross_notional_usd": signed_positions.abs().sum(),
            "net_notional_usd": signed_positions.sum(),
        })

    result = pd.DataFrame(records)

    if not result.empty:
        result = result.sort_values("date").reset_index(drop=True)

        result["rolling_exceptions"] = (
            result["exception"]
            .rolling(BACKTEST_WINDOW_DAYS, min_periods=1)
            .sum()
        )

        # Important: this is only a formal Basel-style zone after enough observations.
        result["traffic_light_zone"] = result["rolling_exceptions"].apply(
            lambda n: classify_zone(int(n))
        )

    return result


def main() -> None:
    returns = load_returns_wide()

    print("=== LAYER A: Historical constant-notional portfolio backtest ===")
    layer_a = run_layer_a(returns)
    layer_a.to_csv(OUTPUT_FILE_A, index=False)

    if not layer_a.empty:
        latest = layer_a.iloc[-1]
        total_exceptions = int(layer_a["exception"].sum())

        print(f"Layer A portfolio: {LAYER_A_PORTFOLIO}")
        print(
            f"Latest rolling exceptions ({BACKTEST_WINDOW_DAYS}d window): "
            f"{int(latest['rolling_exceptions'])} -> {latest['traffic_light_zone']}"
        )
        print(f"Total exceptions in Layer A sample: {total_exceptions}")

    print(f"Saved to {OUTPUT_FILE_A}\n")

    print("=== LAYER B: Live portfolio backtest ===")
    layer_b = run_layer_b(returns)
    layer_b.to_csv(OUTPUT_FILE_B, index=False)

    if layer_b.empty:
        print("No live exception data yet - need positions.csv history.")
    else:
        num_exceptions = int(layer_b["exception"].sum())
        num_days = len(layer_b)
        latest = layer_b.iloc[-1]

        print(f"Live portfolio exceptions so far: {num_exceptions} out of {num_days} days")
        print(
            f"Latest rolling exceptions: "
            f"{int(latest['rolling_exceptions'])} -> {latest['traffic_light_zone']}"
        )
        print(
            "Note: if live history has fewer than 250 observations, this is not yet "
            "a formal Basel traffic-light test. It is live exception monitoring."
        )

    print(f"Saved to {OUTPUT_FILE_B}")


if __name__ == "__main__":
    main()